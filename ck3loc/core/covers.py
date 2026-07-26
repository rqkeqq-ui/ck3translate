"""Обложки модов из мастерской Steam: загрузка и локальный кэш.

Без интернета приложение работает как обычно — просто без картинок.
"""

from __future__ import annotations

from pathlib import Path

from .db import data_dir
from .workshop_api import fetch_details

MAX_BYTES = 4 * 1024 * 1024


def covers_dir() -> Path:
    d = data_dir() / "covers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cached_cover(mod_id: str) -> Path | None:
    p = covers_dir() / f"{mod_id}.jpg"
    return p if p.exists() and p.stat().st_size > 0 else None


def _download(url: str, dest: Path) -> bool:
    try:
        import httpx

        with httpx.stream("GET", url, timeout=20.0, follow_redirects=True) as r:
            r.raise_for_status()
            size = 0
            tmp = dest.with_suffix(".part")
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        tmp.unlink(missing_ok=True)
                        return False
                    f.write(chunk)
            tmp.replace(dest)
            return True
    except Exception:  # noqa: BLE001 — обложка не критична
        return False


def ensure_cover(mod_id: str) -> Path | None:
    """Вернуть путь к обложке, при необходимости скачав её один раз."""
    cached = cached_cover(mod_id)
    if cached:
        return cached
    details = fetch_details([mod_id])
    item = details.get(str(mod_id))
    if item is None or not item.preview_url:
        return None
    dest = covers_dir() / f"{mod_id}.jpg"
    return dest if _download(item.preview_url, dest) else None


def ensure_covers(mod_ids: list[str], progress_cb=None) -> dict[str, Path]:
    """Пакетная загрузка: один запрос к API на сотню модов."""
    result: dict[str, Path] = {}
    todo: list[str] = []
    for mod_id in mod_ids:
        cached = cached_cover(mod_id)
        if cached:
            result[mod_id] = cached
        else:
            todo.append(mod_id)
    if not todo:
        return result
    for start in range(0, len(todo), 100):
        batch = todo[start : start + 100]
        details = fetch_details(batch)
        for i, mod_id in enumerate(batch, start=1):
            if progress_cb:
                progress_cb(start + i, len(todo))
            item = details.get(str(mod_id))
            if item is None or not item.preview_url:
                continue
            dest = covers_dir() / f"{mod_id}.jpg"
            if _download(item.preview_url, dest):
                result[mod_id] = dest
    return result
