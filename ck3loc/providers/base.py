"""Единый интерфейс провайдера перевода.

Провайдер получает тексты с уже защищёнными игровыми кодами
(маркеры вида ⟦T1⟧) и обязан вернуть список переводов той же длины.
"""

from __future__ import annotations

from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Понятная пользователю ошибка провайдера."""


@dataclass
class ProviderInfo:
    name: str
    title: str
    needs_key: bool
    wave: int  # 1 — классический МП, 2 — LLM


class TranslationProvider:
    info = ProviderInfo("base", "База", needs_key=False, wave=1)
    # сколько строк отправлять за один запрос
    batch_size = 40

    def __init__(self, api_key: str = "", **options):
        self.api_key = api_key
        self.options = options

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        glossary: list[tuple[str, str]] | None = None,
        context_types: list[str] | None = None,
    ) -> list[str]:
        raise NotImplementedError


# языковые коды для внешних API
LANG_CODES = {
    "english": "en", "french": "fr", "german": "de", "spanish": "es",
    "russian": "ru", "simp_chinese": "zh", "korean": "ko",
    "polish": "pl", "japanese": "ja",
}


def lang_code(lang: str) -> str:
    return LANG_CODES.get(lang, lang[:2])
