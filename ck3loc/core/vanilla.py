"""Установленная CK3: путь, доступные языки, ванильная локализация."""

from __future__ import annotations

from pathlib import Path

from .locparser import LocFile
from .scanner import DEFAULT_LANGUAGES
from .steam import find_steam_root, steam_libraries


def find_ck3_game_dir(steam_root: Path | None = None) -> Path | None:
    """Папка game установленной CK3 (…/common/Crusader Kings III/game)."""
    root = steam_root or find_steam_root()
    if root is None:
        return None
    for lib in steam_libraries(root):
        cand = lib / "steamapps" / "common" / "Crusader Kings III" / "game"
        if (cand / "localization").is_dir():
            return cand
    return None


def game_languages(game_dir: Path | None = None) -> list[str]:
    """Языки, которые поддерживает установленная игра; иначе резервный список."""
    game = game_dir or find_ck3_game_dir()
    if game is None:
        return list(DEFAULT_LANGUAGES)
    loc = game / "localization"
    # jomini — служебная папка движка, не язык
    service_dirs = {"jomini", "replace"}
    langs = [
        d.name.lower()
        for d in sorted(loc.iterdir())
        if d.is_dir()
        and not d.name.startswith(".")
        and d.name.lower() not in service_dirs
    ]
    return langs or list(DEFAULT_LANGUAGES)


def load_vanilla_index(
    language: str, game_dir: Path | None = None
) -> dict[str, str]:
    """Все ключи ванильной локализации языка: key -> value.

    Ленивая, в память; используется для подстановки официальных
    переводов и как источник терминов глоссария.
    """
    game = game_dir or find_ck3_game_dir()
    if game is None:
        return {}
    lang_dir = game / "localization" / language
    if not lang_dir.is_dir():
        return {}
    index: dict[str, str] = {}
    for path in lang_dir.rglob("*.yml"):
        try:
            loc = LocFile.load(path)
        except OSError:
            continue
        for e in loc.entries():
            # первое вхождение побеждает, replace-файлы ванили редки
            index.setdefault(e.key, e.value)
    return index
