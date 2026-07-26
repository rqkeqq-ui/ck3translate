"""Локализация интерфейса.

Ключ перевода — русский текст: так интерфейс работает без словаря, а новый
язык добавляется файлом ck3loc/lang/<код>.json без правки кода.
"""

from __future__ import annotations

import json
from pathlib import Path

# код языка UI → (название на этом языке, язык локализации CK3)
UI_LANGUAGES: dict[str, tuple[str, str]] = {
    "ru": ("Русский", "russian"),
    "en": ("English", "english"),
    "es": ("Español", "spanish"),
    "fr": ("Français", "french"),
    "de": ("Deutsch", "german"),
    "zh": ("简体中文", "simp_chinese"),
    "ko": ("한국어", "korean"),
}

DEFAULT_UI_LANG = "ru"

_current = DEFAULT_UI_LANG
_table: dict[str, str] = {}


def lang_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "lang"


def available_languages() -> list[tuple[str, str]]:
    """[(код, название)] — все языки интерфейса."""
    return [(code, title) for code, (title, _loc) in UI_LANGUAGES.items()]


def ck3_language_for(ui_code: str) -> str:
    """Какой язык локализации CK3 соответствует языку интерфейса."""
    return UI_LANGUAGES.get(ui_code, UI_LANGUAGES[DEFAULT_UI_LANG])[1]


def system_language() -> str:
    """Язык системы, если он нам знаком (подсказка при первом запуске)."""
    import locale

    try:
        code = (locale.getlocale()[0] or "")[:2].lower()
        if code not in UI_LANGUAGES:
            # на Windows getlocale может вернуть «Russian_Russia»
            name = (locale.getlocale()[0] or "").lower()
            for c, (_title, _loc) in UI_LANGUAGES.items():
                if name.startswith(_loc[:6]):
                    code = c
                    break
    except Exception:  # noqa: BLE001
        code = ""
    return code if code in UI_LANGUAGES else DEFAULT_UI_LANG


def _load_table(code: str) -> dict[str, str]:
    path = lang_dir() / f"{code}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


def set_language(code: str) -> None:
    """Загрузить язык интерфейса.

    Чего нет в словаре языка — берётся из английского, а чего нет и там —
    остаётся исходным русским текстом.
    """
    global _current, _table
    _current = code if code in UI_LANGUAGES else DEFAULT_UI_LANG
    if _current == DEFAULT_UI_LANG:
        _table = {}   # русский — исходный текст, словарь не нужен
        return
    _table = _load_table("en") if _current != "en" else {}
    _table.update(_load_table(_current))


def current_language() -> str:
    return _current


def tr(text: str) -> str:
    """Перевести строку интерфейса; без перевода вернуть как есть."""
    return _table.get(text, text)


def tr_format(text: str, **kwargs) -> str:
    """Перевод с подстановкой: tr_format('Найдено {n}', n=5)."""
    try:
        return tr(text).format(**kwargs)
    except (KeyError, IndexError):
        return tr(text)
