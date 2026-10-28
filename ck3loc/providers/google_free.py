"""Google Translate без ключа API через публичный веб-шлюз переводчика.

Тот же шлюз используют браузерные расширения (client=gtx). Он неофициальный:
Google может ограничить частые запросы (HTTP 429) или изменить ответ, поэтому
строки идут по одной с паузой, а при ограничении задание ставится на паузу —
готовые строки сохраняются, продолжить можно позже.
"""

from __future__ import annotations

import re
import threading
import time

from ck3loc.core import net

from .base import ProviderError, ProviderInfo, ProviderPaused, TranslationProvider, lang_code

_URL = "https://translate.googleapis.com/translate_a/single"
# Google портит маркеры: вставляет пробелы («⟦ T1 ⟧») и при переводе на русский
# заменяет латинскую T на кириллическую («⟦Т1⟧»), реже на греческую или строчную.
_SPACED_MARK = re.compile(r"⟦\s*[TtТтΤτ]\s*(\d+)\s*⟧")
# В строке только коды, цифры и знаки — переводить нечего, запрос не нужен.
_NOTHING_TO_TRANSLATE = re.compile(r"(?:⟦T\d+⟧|[\W\d_])*")
_RETRY_STATUSES = {429, 500, 502, 503, 504}
LIMITED = ("Google временно ограничил бесплатные запросы с вашего IP-адреса; готовые строки сохранены. "
           "Продолжите позже через «Историю действий» или увеличьте паузу между запросами")


_EDGE = re.compile(r"^((?:\s|⟦T\d+⟧)*)(.*?)((?:\s|⟦T\d+⟧)*)$", re.S)


def split_edges(text: str) -> tuple[str, str, str]:
    """(начало, середина, конец): коды и пробелы по краям в сервис не отправляются.

    Веб-переводчики теряют маркеры на краях строки («#n Disabled#!» → без тегов);
    переводится только середина, края возвращаются как есть.
    """
    head, core, tail = _EDGE.match(text).groups()
    return head, core, tail


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
    # По строке на пачку: шлюз переводит по одной строке, а окно показывает ход после каждой.
    batch_size = 1
    delay = 0.35       # пауза между запросами — и между пачками, чтобы не получить бан по IP
    retries = 4
    # Параллельные запросы к публичному шлюзу живьём дают бан по IP (302 на google.com/sorry).
    max_workers = 1

    def __init__(self, api_key: str = "", **options):
        super().__init__(api_key, **options)
        self._client = None
        self._client_lock = threading.Lock()
        self._last_request: float | None = None

    def _http(self):
        """Одно соединение на задание: без нового TLS-рукопожатия (через прокси ~1,5 с) на каждую строку."""
        with self._client_lock:
            if self._client is None:
                self._client = net.client(_URL, timeout=30.0)
            return self._client

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        source, target = lang_code(source_lang), lang_code(target_lang)
        result = []
        for text in texts:
            if _NOTHING_TO_TRANSLATE.fullmatch(text):
                result.append(text)
                continue
            now = time.monotonic()
            if self._last_request is not None and (wait := self.delay - (now - self._last_request)) > 0:
                time.sleep(wait)
            head, core, tail = split_edges(text)
            try:
                result.append(head + self._translate(core, source, target) + tail)
            finally:
                self._last_request = time.monotonic()
        return result

    def _translate(self, text: str, source: str, target: str) -> str:
        import httpx

        for attempt in range(self.retries):
            try:
                resp = self._http().post(_URL, params={"client": "gtx", "sl": source, "tl": target, "dt": "t"},
                                         data={"q": text})
            except httpx.HTTPError as exc:
                raise ProviderPaused("Google Translate (бесплатно): нет соединения; продолжите позже") from exc
            if resp.status_code in (301, 302, 303) and '/sorry' in resp.headers.get('location', ''):
                # Проверка «необычный трафик»: повторы только продлевают блокировку.
                raise ProviderPaused(LIMITED)
            if resp.status_code in _RETRY_STATUSES and attempt + 1 < self.retries:
                time.sleep(2 * 2 ** attempt)
                continue
            if resp.status_code == 429:
                raise ProviderPaused(LIMITED)
            if resp.status_code != 200:
                raise ProviderPaused(f"Google Translate (бесплатно): HTTP {resp.status_code}")
            try:
                payload = resp.json()
            except ValueError as exc:
                raise ProviderError("Google Translate (бесплатно) вернул неожиданный ответ.") from exc
            return normalize_marks(parse_response(payload))
        raise ProviderPaused("Google Translate (бесплатно) недоступен; продолжите позже")
