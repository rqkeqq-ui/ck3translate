"""Discover Workshop and local launcher mods without modifying their files."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import settings
from .descriptor import _FIELD_RE
from .steam import find_steam_root, workshop_content_dirs


def documents_dir() -> Path:
    if sys.platform == "win32":
        try:
            folder_id = ctypes.create_string_buffer(uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7").bytes_le)
            result = ctypes.c_void_p()
            shell = ctypes.windll.shell32.SHGetKnownFolderPath
            shell.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
            shell.restype = ctypes.c_long
            if shell(folder_id, 0, None, ctypes.byref(result)) == 0:
                try:
                    return Path(ctypes.wstring_at(result))
                finally:
                    free = ctypes.windll.ole32.CoTaskMemFree
                    free.argtypes = [ctypes.c_void_p]
                    free(result)
        except (AttributeError, OSError, ValueError):
            pass
    return Path.home() / "Documents"


def local_mods_dir() -> Path:
    override = os.environ.get("CK3LOC_PDX_MOD_DIR") or settings.get("local_mods_path")
    if override:
        return Path(override).expanduser()
    base = Path.home() / ".local/share" if sys.platform == "linux" else documents_dir()
    return base / "Paradox Interactive" / "Crusader Kings III" / "mod"


def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


@dataclass(frozen=True)
class InstalledMod:
    mod_id: str
    path: Path
    source: str


@dataclass
class LibraryResult:
    mods: list[InstalledMod] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    complete: bool = True
    complete_roots: list[Path] = field(default_factory=list)


def discover_mods(steam_path: Path | None = None, local_path: Path | None = None) -> LibraryResult:
    result = LibraryResult()
    seen: set[str] = set()

    def add(path: Path, source: str) -> None:
        try:
            key = path_key(path)
            if key in seen:
                return
            path.stat()
            if not path.is_dir():
                raise FileNotFoundError('Mod directory does not exist')
            # Exclude data-only databases and our generated translation patches.
            if (path / "ck3loc-database.json").is_file():
                return
            manifest = path / ".ck3loc/manifest.json"
            if manifest.is_file():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict) and all(k in data for k in ("mod_id", "source_lang", "target_lang", "keys")):
                    return
            seen.add(key)
            mod_id = path.name if source == "workshop" else "local_" + hashlib.sha256(key.encode("utf-8")).hexdigest()
            result.mods.append(InstalledMod(mod_id, path.resolve(), source))
        except FileNotFoundError as exc:
            result.warnings.append(f'{path}: {exc}')
        except (OSError, ValueError, RuntimeError) as exc:
            result.complete = False
            result.warnings.append(f"{path}: {exc}")

    configured = steam_path or (Path(settings.get("steam_path")) if settings.get("steam_path") else None)
    steam = find_steam_root(configured)
    if configured and steam is None:
        result.complete = False
        result.warnings.append(f"Steam: {configured}")
    if steam:
        for content in workshop_content_dirs(steam):
            was_complete = result.complete
            result.complete = True
            try:
                for child in sorted(content.iterdir()):
                    if child.is_dir() and child.name.isdigit():
                        add(child, "workshop")
            except OSError as exc:
                result.complete = False
                result.warnings.append(f"{content}: {exc}")
            if result.complete:
                result.complete_roots.append(content.resolve())
            result.complete = result.complete and was_complete
    root = local_path if local_path is not None else local_mods_dir()
    other_roots_complete = result.complete
    result.complete = True
    try:
        children = sorted(root.iterdir())
    except FileNotFoundError:
        if local_path is not None or settings.get("local_mods_path"):
            result.complete = False
            result.warnings.append(f"Local mod directory not found: {root}")
        return result
    except OSError as exc:
        result.complete = False
        result.warnings.append(f"{root}: {exc}")
        return result
    for child in children:
        if child.is_dir() and ((child / "descriptor.mod").is_file() or (child / "localization").is_dir()):
            add(child, "local")
        elif child.is_file() and child.suffix.lower() == ".mod":
            try:
                fields = dict(_FIELD_RE.findall(child.read_text(encoding="utf-8-sig")))
                from .community_db import configured_workshop_id
                if fields.get('remote_file_id') == configured_workshop_id():
                    continue
                value = fields.get("path", "").replace('\\"', '"').replace("\\\\", "\\")
                if not value:
                    if fields.get('archive'):
                        from .i18n import tr
                        result.warnings.append(f"{child.name}: {tr('Архивный мод: перевод архивов пока не поддерживается')}")
                        continue
                    raise ValueError("Missing path in launcher descriptor")
                target = Path(value.replace("\\", "/")).expanduser()
                add(target if target.is_absolute() else root.parent / target, "local")
            except (OSError, ValueError) as exc:
                if isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError):
                    result.complete = False
                result.warnings.append(f"{child}: {exc}")
    if result.complete:
        result.complete_roots.append(root.resolve())
    result.complete = result.complete and other_roots_complete
    return result
