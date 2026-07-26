"""LLM-провайдеры: Anthropic (Claude) и любой OpenAI-совместимый endpoint.

Переводят с учётом глоссария и типа строки; ответ — строгий JSON-массив.
"""

from __future__ import annotations

import json

from .base import ProviderError, ProviderInfo, TranslationProvider

_LANG_NAMES = {
    "english": "английского", "french": "французского", "german": "немецкого",
    "spanish": "испанского", "russian": "русский", "simp_chinese": "китайского",
    "korean": "корейского", "polish": "польского", "japanese": "японского",
}

_SYSTEM = """Ты — профессиональный переводчик модов Crusader Kings 3.
Правила:
1. Маркеры вида ⟦T1⟧ — защищённые игровые коды: переноси их в перевод без изменений, не переводить и не удалять.
2. Литеральную последовательность \\n сохраняй как есть.
3. Тип строки подсказывает стиль: name/title — краткое название; desc — описание; rule — правило игры; tooltip — подсказка.
4. Соблюдай глоссарий, если он дан.
5. Верни ТОЛЬКО JSON-массив строк-переводов той же длины и в том же порядке, без пояснений."""


def _build_user_prompt(texts, source_lang, target_lang, glossary, context_types):
    src = _LANG_NAMES.get(source_lang, source_lang)
    tgt = _LANG_NAMES.get(target_lang, target_lang)
    parts = [f"Переведи с {src} на {tgt}."]
    if glossary:
        parts.append("Глоссарий (обязательно):")
        parts.extend(f"  {s} → {t}" for s, t in glossary[:80])
    items = []
    for i, text in enumerate(texts):
        t = (context_types[i] if context_types and i < len(context_types)
             else "text")
        items.append({"type": t, "text": text})
    parts.append("Строки (JSON):")
    parts.append(json.dumps(items, ensure_ascii=False))
    return "\n".join(parts)


def _parse_array(raw: str, expected: int) -> list[str]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ProviderError("LLM вернула не JSON-массив.")
    try:
        arr = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise ProviderError(f"LLM вернула повреждённый JSON: {e.msg}") from e
    if not isinstance(arr, list) or len(arr) != expected:
        raise ProviderError(
            f"LLM вернула {len(arr) if isinstance(arr, list) else '?'} строк "
            f"вместо {expected}."
        )
    return [str(x) for x in arr]


class AnthropicProvider(TranslationProvider):
    info = ProviderInfo("claude", "Claude (Anthropic API)", needs_key=True, wave=2)
    batch_size = 30

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        import httpx

        if not self.api_key:
            raise ProviderError("Не задан API-ключ Anthropic. Настройки → ключи.")
        model = self.options.get("model") or "claude-sonnet-5"
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": 8000,
                    "system": _SYSTEM,
                    "messages": [{
                        "role": "user",
                        "content": _build_user_prompt(
                            texts, source_lang, target_lang, glossary,
                            context_types),
                    }],
                },
                timeout=180.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Anthropic: HTTP {e.response.status_code} — "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"Anthropic: сетевая ошибка ({e})") from e
        blocks = payload.get("content", [])
        raw = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return _parse_array(raw, len(texts))


class OpenAICompatProvider(TranslationProvider):
    info = ProviderInfo("openai", "LLM (OpenAI-совместимый API)",
                        needs_key=True, wave=2)
    batch_size = 30

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        import httpx

        if not self.api_key:
            raise ProviderError("Не задан API-ключ. Настройки → ключи.")
        base_url = (self.options.get("base_url")
                    or "https://api.openai.com/v1").rstrip("/")
        model = self.options.get("model") or "gpt-4o-mini"
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": _build_user_prompt(
                            texts, source_lang, target_lang, glossary,
                            context_types)},
                    ],
                },
                timeout=180.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"LLM API: HTTP {e.response.status_code} — "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"LLM API: сетевая ошибка ({e})") from e
        raw = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_array(raw, len(texts))
