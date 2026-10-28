"""Бесплатные веб-переводчики через библиотеку translators (UlionTse, GPL-3.0).

Библиотека обращается к веб-версиям сервисов без ключа API. Это неофициальные
пути: сервис может ограничить частые запросы или изменить сайт. Поэтому
строки идут по одной с паузой, параллельных запросов нет, а любая ошибка
сервиса ставит задание на паузу — готовые строки сохраняются.

Набор движков отобран живой проверкой EN→RU с игровыми кодами CK3:
остальные движки библиотеки ломают маркеры ⟦Tn⟧ или не поддерживают русский.
"""

from __future__ import annotations

import os
import threading
import time

from ck3loc.core import net

from .base import ProviderError, ProviderInfo, ProviderPaused, TranslationProvider, lang_code
from .google_free import _NOTHING_TO_TRANSLATE, normalize_marks, split_edges

_IMPORT_LOCK = threading.Lock()


def _library():
    """Загрузить translators по требованию (импорт ~2 с) без определения региона по сети.

    Без translators_default_region библиотека при первом запросе отправляет
    IP-адрес сторонним сервисам геолокации, чтобы выбрать сервер.
    """
    with _IMPORT_LOCK:
        os.environ.setdefault('translators_default_region', 'EN')
        import translators
        return translators


class WebFreeProvider(TranslationProvider):
    engine = ''
    url = ''           # адрес сервиса — для выбора системного прокси
    batch_size = 20
    delay = 0.5        # пауза между строками
    max_workers = 1    # параллельные запросы к веб-версиям приводят к бану по IP

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        source, target = lang_code(source_lang), lang_code(target_lang)
        result, sent = [], 0
        for text in texts:
            if not text.strip() or _NOTHING_TO_TRANSLATE.fullmatch(text):
                result.append(text)
                continue
            if sent:
                time.sleep(self.delay)
            head, core, tail = split_edges(text)
            result.append(head + self._translate(core, source, target) + tail)
            sent += 1
        return result

    def _translate(self, text: str, source: str, target: str) -> str:
        title = self.info.title.split(' · ')[0]
        try:
            ts = _library()
        except ImportError as exc:
            raise ProviderError(f'{title}: не установлена библиотека translators ({exc})') from exc
        proxy = net.proxy_for(self.url)
        try:
            answer = ts.translate_text(text, translator=self.engine, from_language=source, to_language=target,
                                       proxies={'http': proxy, 'https': proxy} if proxy else {},
                                       http_client='requests', timeout=30)
        except Exception as exc:  # noqa: BLE001 — сервис ограничил запросы, изменил сайт или недоступен
            raise ProviderPaused(f'{title} (бесплатно) не ответил: {type(exc).__name__}: {str(exc)[:160]}. '
                                 'Готовые строки сохранены, продолжите позже или выберите другой переводчик') from exc
        if not isinstance(answer, str):
            raise ProviderPaused(f'{title} (бесплатно) вернул неожиданный ответ')
        return normalize_marks(answer)


def _provider(name: str, title: str, engine: str, url: str) -> type[WebFreeProvider]:
    return type(f'{engine.title()}FreeProvider', (WebFreeProvider,), {
        'info': ProviderInfo(name, title, needs_key=False, wave=1), 'engine': engine, 'url': url,
        '__doc__': f'{title} через translators.'})


BingFreeProvider = _provider('bing_free', 'Bing Translator · бесплатно', 'bing', 'https://www.bing.com/translator')
GoogleWebFreeProvider = _provider('google_web_free', 'Google (веб-версия) · бесплатно', 'google',
                                  'https://translate.google.com')
YandexFreeProvider = _provider('yandex_free', 'Яндекс Переводчик · бесплатно', 'yandex', 'https://translate.yandex.com')
AlibabaFreeProvider = _provider('alibaba_free', 'Alibaba · бесплатно', 'alibaba', 'https://translate.alibaba.com')
WEB_FREE_PROVIDERS = (BingFreeProvider, GoogleWebFreeProvider, YandexFreeProvider, AlibabaFreeProvider)
