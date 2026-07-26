"""Google Cloud Translation (v2, API-ключ)."""

from __future__ import annotations

from .base import ProviderError, ProviderInfo, TranslationProvider, lang_code

_URL = "https://translation.googleapis.com/language/translate/v2"


class GoogleProvider(TranslationProvider):
    info = ProviderInfo("google", "Google Cloud Translation", needs_key=True, wave=1)
    batch_size = 60

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        import httpx

        if not self.api_key:
            raise ProviderError("Не задан API-ключ Google. Настройки → ключи.")
        try:
            resp = httpx.post(
                _URL,
                params={"key": self.api_key},
                json={
                    "q": texts,
                    "source": lang_code(source_lang),
                    "target": lang_code(target_lang),
                    "format": "text",
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Google Translate: HTTP {e.response.status_code} — "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"Google Translate: сетевая ошибка ({e})") from e
        items = payload.get("data", {}).get("translations", [])
        if len(items) != len(texts):
            raise ProviderError("Google Translate вернул не все строки.")
        return [i.get("translatedText", "") for i in items]
