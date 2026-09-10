"""Поиск Steam, библиотек и папки мастерской CK3.

Всё здесь — только чтение. Файлы Steam (.vdf/.acf) разбираются как
фактический внутренний формат: терпимо к незнакомому содержимому.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CK3_APP_ID = "1158310"

_KV_RE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*"((?:[^"\\]|\\.)*)"')


def _unescape(s: str) -> str:
    return s.replace("\\\\", "\\").replace('\\"', '"')


def find_steam_root(override: Path | None = None) -> Path | None:
    """Найти корень Steam: явный путь → реестр → стандартные места."""
    if override:
        p = Path(override)
        return p if p.exists() else None
    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for value_name in ("SteamPath", "InstallPath"):
                        try:
                            v, _ = winreg.QueryValueEx(k, value_name)
                            p = Path(v)
                            if p.exists():
                                return p
                        except OSError:
                            continue
            except OSError:
                continue
    except ImportError:
        pass
    for cand in (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path.home() / ".local/share/Steam",
        Path.home() / ".steam/steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        Path.home() / "Library/Application Support/Steam",
    ):
        if cand.exists():
            return cand
    return None


def steam_libraries(steam_root: Path) -> list[Path]:
    """Все библиотеки Steam (включая корневую) из libraryfolders.vdf."""
    libs: list[Path] = []
    root_steamapps = steam_root / "steamapps"
    if root_steamapps.exists():
        libs.append(steam_root)
    vdf = root_steamapps / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for m in _KV_RE.finditer(text):
            k, v = m.group(1).lower(), _unescape(m.group(2))
            if k == "path":
                p = Path(v)
                if p.exists() and p not in libs:
                    libs.append(p)
    return libs


def workshop_content_dirs(
    steam_root: Path | None = None, app_id: str = CK3_APP_ID
) -> list[Path]:
    """Папки workshop/content/<app_id> во всех библиотеках."""
    root = steam_root or find_steam_root()
    if root is None:
        return []
    out = []
    for lib in steam_libraries(root):
        d = lib / "steamapps" / "workshop" / "content" / app_id
        if d.is_dir():
            out.append(d)
    return out


def list_workshop_mod_dirs(content_dirs: list[Path]) -> list[Path]:
    """Числовые подпапки (ID модов) во всех папках content."""
    mods = []
    for content in content_dirs:
        try:
            for child in sorted(content.iterdir()):
                if child.is_dir() and child.name.isdigit():
                    mods.append(child)
        except OSError:
            continue
    return mods


@dataclass
class AcfEntry:
    """Запись из appworkshop_<app_id>.acf (вспомогательный сигнал версии)."""

    item_id: str
    size: str = ""
    time_updated: str = ""
    manifest: str = ""


def read_workshop_acf(
    steam_root: Path | None = None, app_id: str = CK3_APP_ID
) -> dict[str, AcfEntry]:
    """Простое извлечение timeupdated/manifest по ID из ACF.

    Формат Valve читаем без строгой грамматики: ищем блоки верхнего
    уровня вида "<id>" { ... } внутри WorkshopItemsInstalled.
    """
    root = steam_root or find_steam_root()
    if root is None:
        return {}
    result: dict[str, AcfEntry] = {}
    for lib in steam_libraries(root):
        acf = lib / "steamapps" / "workshop" / f"appworkshop_{app_id}.acf"
        if not acf.exists():
            continue
        try:
            text = acf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        section = text
        m = re.search(r'"WorkshopItemsInstalled"\s*\{', text)
        if m:
            section = text[m.end() :]
        for bm in re.finditer(
            r'"(\d+)"\s*\{([^{}]*)\}', section, flags=re.DOTALL
        ):
            item_id, body = bm.group(1), bm.group(2)
            entry = result.setdefault(item_id, AcfEntry(item_id=item_id))
            for km in _KV_RE.finditer(body):
                k, v = km.group(1).lower(), km.group(2)
                if k == "size":
                    entry.size = v
                elif k == "timeupdated":
                    entry.time_updated = v
                elif k == "manifest":
                    entry.manifest = v
    return result
