"""Настройки приложения (несекретные) в JSON рядом с базой.

Секреты (API-ключи) здесь не хранятся — только в Windows Credential Manager.
"""

from __future__ import annotations

import json
from pathlib import Path

from .db import data_dir

DEFAULTS: dict = {
    "source_lang": "english",
    "target_lang": "russian",
    "write_mode": "in_mod",       # in_mod | patch_mod
    "build_mode": "auto",         # auto | full | delta
    "provider": "google",
    "steam_path": "",             # пусто — определять автоматически
    "theme": "dark",              # dark | light
    "scan_on_start": True,
    "openai_base_url": "",
    "openai_model": "",
    "claude_model": "",
    "yandex_folder_id": "",
    # обнаружение модов-русификаторов
    "provider_detect": True,
    "provider_min_ratio": 0.25,
    "provider_min_keys": 30,
    "community_db_enabled": True,
    "show_covers_in_list": False,
    "fetch_covers": True,          # загружать обложки модов из мастерской
    "ui_lang": "",                 # пусто — язык ещё не выбран (первый запуск)
}


def _path() -> Path:
    return data_dir() / "settings.json"


def load() -> dict:
    data = dict(DEFAULTS)
    p = _path()
    if p.exists():
        try:
            data.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save(values: dict) -> None:
    data = load()
    data.update(values)
    _path().write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set_value(key: str, value) -> None:
    save({key: value})
