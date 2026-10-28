"""Google Translate без ключа API через публичный веб-шлюз переводчика.

Тот же шлюз используют браузерные расширения (client=gtx). Он неофициальный:
Google может ограничить частые запросы (HTTP 429) или изменить ответ, поэтому
строки идут по одной с паузой, а при ограничении задание ставится на паузу —
готовые строки сохраняются, продолжить можно позже.
"""

from __future__ import annotations

import re
import time

from ck3loc.core import net

from .base import ProviderError, ProviderInfo, ProviderPaused, TranslationProvider, lang_code

_URL = "https://translate.googleapis.com/translate_a/single"
# Google иногда вставляет пробелы внутрь маркеров: «⟦ T1 ⟧», «⟦T 1⟧».
_SPACED_MARK = re.compile(r"⟦\s*T\s*(\d+)\s*⟧")
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def normalize_marks(text: str) -> str:
    return _SPACED_MARK.sub(lambda m: f"⟦T{m.group(1)}⟧", text)


def parse_response(payload) -> str:
    """Ответ — вложенный массив: [[["перевод", "исходник", ...], ...], ...]."""
    try:
        return "".join(seg[0] for seg in payload[0] if seg and isinstance(seg[0], str))
    except (TypeError, IndexError, KeyError) as exc:
        raise ProviderError("Google Translate (бесплатно) вернул неожиданный ответ.") from exc


class GoogleFreeProvider(TranslationProvider):
    info = ProviderInfo("google_free", "Google Translate · бесплатно", needs_key=False, wave=1)
    batch_size = 20
    delay = 0.35       # пауза между строками, чтобы не получить временный бан по IP
    retries = 4

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        source, target = lang_code(source_lang), lang_code(target_lang)
        result = []
        for i, text in enumerate(texts):
            if i:
                time.sleep(self.delay)
            result.append(self._translate(text, source, target) if text.strip() else text)
        return result

    def _translate(self, text: str, source: str, target: str) -> str:
        import httpx

        for attempt in range(self.retries):
            try:
                resp = net.post(_URL, params={"client": "gtx", "sl": source, "tl": target, "dt": "t"},
                                data={"q": text}, timeout=30.0)
            except httpx.HTTPError as exc:
                raise ProviderPaused("Google Translate (бесплатно): нет соединения; продолжите позже") from exc
            if resp.status_code in _RETRY_STATUSES and attempt + 1 < self.retries:
                time.sleep(2 * 2 ** attempt)
                continue
            if resp.status_code == 429:
                raise ProviderPaused("Google временно ограничил бесплатные запросы (HTTP 429); "
                                     "готовые строки сохранены, продолжите позже")
            if resp.status_code != 200:
                raise ProviderPaused(f"Google Translate (бесплатно): HTTP {resp.status_code}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ProviderError("Google Translate (бесплатно) вернул неожиданный ответ.") from exc
            return normalize_marks(parse_response(payload))
        raise ProviderPaused("Google Translate (бесплатно) недоступен; продолжите позже")
