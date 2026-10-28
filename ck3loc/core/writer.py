"""Запись перевода: режим «внутрь мода» (по умолчанию) и патч-мод.

Железные правила: файлы автора никогда не изменяются; всё записанное
регистрируется в базе и восстановимо; запись атомарна с бэкапом.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .atomicio import write_atomic
from .db import backups_dir
from .descriptor import render_descriptor
from .locparser import build_new_file
from .scanner import ModScan, semantic_hash
from .status import WRITABLE
from .store import set_unit_written_hash
from .tokens import validate_translation

IN_MOD = "in_mod"
PATCH_MOD = "patch_mod"


def pdx_mod_dir() -> Path:
    """Пользовательская папка модов CK3 (для патч-модов)."""
    from .mod_library import local_mods_dir

    return local_mods_dir()


@dataclass
class PlannedFile:
    abs_path: Path
    data: bytes
    keys: list[str]
    kind: str  # "new_lang" | "replace" | "descriptor" | "dot_mod" | "manifest"


@dataclass
class WritePlan:
    write_mode: str
    build_mode: str  # full | delta (после автоопределения)
    files: list[PlannedFile] = field(default_factory=list)
    skipped_keys: list[tuple[str, str]] = field(default_factory=list)  # (key, причина)
    delete_paths: list[Path] = field(default_factory=list)
    baselines: dict[str, str | None] = field(default_factory=dict)
    path_mappings: dict[str, str] = field(default_factory=dict)

    @property
    def total_keys(self) -> int:
        return sum(len(f.keys) for f in self.files if f.kind in ("new_lang", "replace"))


def _mirror_name(rel_path: str, source_lang: str, target_lang: str) -> str:
    """EPE_common_l_english.yml → EPE_common_l_russian.yml"""
    name = Path(rel_path).name
    suffix = f"_l_{source_lang}.yml"
    if name.lower().endswith(suffix):
        return name[: -len(suffix)] + f"_l_{target_lang}.yml"
    return Path(name).stem + f"_l_{target_lang}.yml"


def build_write_plan(
    scan: ModScan,
    project: dict,
    units: dict,
    build_mode: str = "auto",
    has_external_provider: bool = False,
) -> WritePlan:
    """Составить план записи. Ничего не пишет — только план и предпросмотр."""
    source_lang = project["source_lang"]
    target_lang = project["target_lang"]
    write_mode = project["write_mode"]
    mod_id = project["mod_id"]

    src = scan.languages.get(source_lang)
    native = scan.languages.get(target_lang)
    native_keys = dict(native.keys) if native else {}
    src_keys = dict(src.keys) if src else {}

    if build_mode == "auto":
        build_mode = "delta" if native_keys else "full"

    plan = WritePlan(write_mode=write_mode, build_mode=build_mode)

    # отбираем пригодные к записи переводы
    writable: dict[str, str] = {}
    for key, unit in units.items():
        unit = dict(unit)
        target_text = unit.get("target_text") or ""
        if not target_text:
            continue
        if unit.get("status") not in WRITABLE and unit.get("status") != "":
            # untranslated с текстом не бывает; approved/reviewed/machine — ок
            if unit.get("status") == "untranslated":
                continue
        occ = src_keys.get(key)
        if occ is None:
            plan.skipped_keys.append((key, "ключ удалён из источника (осиротел)"))
            continue
        errors = validate_translation(occ.value, target_text)
        if errors:
            plan.skipped_keys.append((key, "ошибка кодов: " + "; ".join(errors)))
            continue
        writable[key] = target_text

    # Manager outputs must be excluded from the native scan by callers.
    if build_mode == "delta":
        writable = {
            k: v
            for k, v in writable.items()
            if k not in native_keys or native_keys[k].value != v
        }

    # раскладка: новые ключи зеркалом по файлам источника,
    # переопределения родного языка — в replace
    new_keys = {k: v for k, v in writable.items() if k not in native_keys}
    override_keys = {k: v for k, v in writable.items() if k in native_keys}

    if write_mode == IN_MOD:
        base = scan.mod_dir / "localization"
        lang_dir = base / target_lang
        replace_dir = base / "replace" / target_lang
    else:
        patch_root = pdx_mod_dir() / f"ck3loc_{mod_id}_{target_lang}"
        lang_dir = patch_root / "localization" / "replace" / target_lang
        replace_dir = lang_dir  # в патч-моде всё в replace

    # группировка новых ключей по исходным файлам (зеркальные имена)
    by_file: dict[str, list[tuple[str, str]]] = {}
    for key, value in sorted(new_keys.items()):
        occ = src_keys[key]
        relative = Path(occ.rel_path)
        fname = str(relative.parent / _mirror_name(occ.rel_path, source_lang, target_lang))
        # Mirror nested paths inside the source language directory only.
        parts = relative.parts
        if source_lang in parts:
            fname = str(Path(*parts[parts.index(source_lang) + 1:-1]) /
                        _mirror_name(occ.rel_path, source_lang, target_lang))
        by_file.setdefault(fname, []).append((key, value))

    for fname, items in sorted(by_file.items()):
        # если мод переводит отдельный мод-русификатор, наши файлы обязаны
        # называться иначе: одноимённый файл из мода, загруженного позже,
        # перекрывает наш целиком, и добавленные строки просто исчезнут
        filename = Path(fname)
        fname = str(filename.with_name('zz_ck3loc_' + filename.name))
        target_path = lang_dir / fname
        data = build_new_file(target_lang, items)
        plan.files.append(
            PlannedFile(
                abs_path=target_path,
                data=data,
                keys=[k for k, _v in items],
                kind="new_lang",
            )
        )

    if override_keys:
        items = sorted(override_keys.items())
        fname = f"zz_ck3loc_{mod_id}_fixes_l_{target_lang}.yml"
        plan.files.append(
            PlannedFile(
                abs_path=replace_dir / fname,
                data=build_new_file(target_lang, items),
                keys=[k for k, _v in items],
                kind="replace",
            )
        )

    # служебные файлы патч-мода
    if write_mode == PATCH_MOD and plan.files:
        patch_root = pdx_mod_dir() / f"ck3loc_{mod_id}_{target_lang}"
        mod_name = f"[RU] {scan.name}" if target_lang == "russian" else \
            f"[{target_lang.upper()[:2]}] {scan.name}"
        supported = scan.descriptor.supported_version or "1.*"
        desc_text = render_descriptor(
            mod_name, "1.0", supported, tags=["Translation"]
        ).encode("utf-8")
        plan.files.append(
            PlannedFile(patch_root / "descriptor.mod", desc_text, [], "descriptor")
        )
        dot_mod = render_descriptor(
            mod_name, "1.0", supported, tags=["Translation"],
            path=str(patch_root).replace("\\", "/"),
        ).encode("utf-8")
        plan.files.append(
            PlannedFile(
                pdx_mod_dir() / f"ck3loc_{mod_id}_{target_lang}.mod",
                dot_mod, [], "dot_mod",
            )
        )
        manifest = {
            "mod_id": mod_id,
            "source_lang": project["source_lang"],
            "target_lang": target_lang,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source_descriptor_version": scan.descriptor.version,
            "keys": sorted(writable),
        }
        plan.files.append(
            PlannedFile(
                patch_root / ".ck3loc" / "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"),
                [], "manifest",
            )
        )
    return plan


@dataclass
class WriteResult:
    written: list[Path] = field(default_factory=list)
    backups: list[Path] = field(default_factory=list)


def _latest_outputs(conn, project_id: int):
    return conn.execute('''SELECT * FROM generated_outputs WHERE id IN
        (SELECT MAX(id) FROM generated_outputs WHERE project_id=? GROUP BY abs_path)''',
        (project_id,)).fetchall()


def prepare_write_plan(conn, project_id: int, plan: WritePlan) -> WritePlan:
    """Resolve ownership and collisions before the user sees the file preview."""
    ours = {r['abs_path']: r for r in _latest_outputs(conn, project_id)}
    mappings = {r['logical_path']: r['abs_path'] for r in conn.execute(
        'SELECT * FROM output_paths WHERE project_id=?', (project_id,))}
    reserved = set()
    for pf in plan.files:
        logical = str(pf.abs_path)
        if logical in mappings:
            pf.abs_path = Path(mappings[logical])
        base = pf.abs_path
        n = 0
        while ((pf.abs_path.exists() and str(pf.abs_path) not in ours)
               or str(pf.abs_path) in reserved):
            if pf.kind in {'descriptor', 'dot_mod', 'manifest'}:
                raise ValueError(f'Unowned patch metadata: {pf.abs_path}')
            n += 1
            pf.abs_path = base.with_name(f'zz_ck3loc_{n}_{base.name}')
        reserved.add(str(pf.abs_path))
        plan.path_mappings[logical] = str(pf.abs_path)
    plan.delete_paths = [Path(p) for p, r in ours.items()
                         if p not in reserved and r['write_mode'] == plan.write_mode
                         and Path(p).suffix.lower() == '.yml']
    for p in [f.abs_path for f in plan.files] + plan.delete_paths:
        actual = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None
        if actual is not None and str(p) in ours and actual != ours[str(p)]['file_hash']:
            raise ValueError(f'File edited outside the application: {p}')
        plan.baselines[str(p)] = actual
    return plan


def apply_write_plan(
    conn, project_id: int, plan: WritePlan, scan: ModScan, units: dict, *, commit: bool = True
) -> WriteResult:
    result = WriteResult()
    if not plan.baselines:
        prepare_write_plan(conn, project_id, plan)
    paths = [f.abs_path for f in plan.files] + plan.delete_paths
    originals = {}
    for p in paths:
        data = p.read_bytes() if p.exists() else None
        actual = hashlib.sha256(data).hexdigest()[:16] if data is not None else None
        if actual != plan.baselines[str(p)]:
            raise ValueError(f'File changed after preview: {p}')
        originals[p] = data
    mod_backup = backups_dir() / scan.mod_id / uuid.uuid4().hex
    changed = []
    conn.execute('SAVEPOINT write_outputs')
    try:
        for pf in plan.files:
            backup = write_atomic(pf.abs_path, pf.data, backup_dir=mod_backup)
            changed.append(pf.abs_path)
            if backup:
                result.backups.append(backup)
            result.written.append(pf.abs_path)
            conn.execute(
                """INSERT INTO generated_outputs
                       (project_id, abs_path, file_hash, write_mode, written_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    project_id,
                    str(pf.abs_path),
                    hashlib.sha256(pf.data).hexdigest()[:16],
                    plan.write_mode,
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                ),
            )
            for key in pf.keys:
                unit = units.get(key)
                if unit is not None:
                    set_unit_written_hash(
                        conn, project_id, key,
                        semantic_hash(dict(unit).get("target_text") or ""),
                    )
        for p in plan.delete_paths:
            if p.exists():
                import shutil
                mod_backup.mkdir(parents=True, exist_ok=True)
                backup = mod_backup / (uuid.uuid4().hex + '_' + p.name)
                shutil.copy2(p, backup)
                result.backups.append(backup)
                p.unlink()
                changed.append(p)
            conn.execute('DELETE FROM generated_outputs WHERE project_id=? AND abs_path=?', (project_id, str(p)))
        for logical, path in plan.path_mappings.items():
            conn.execute('''INSERT INTO output_paths VALUES (?,?,?) ON CONFLICT(project_id,logical_path)
                DO UPDATE SET abs_path=excluded.abs_path''', (project_id, logical, path))
        conn.execute('RELEASE write_outputs')
        if commit:
            conn.commit()
    except Exception as error:
        conn.execute('ROLLBACK TO write_outputs')
        conn.execute('RELEASE write_outputs')
        failed = []
        for p in reversed(changed):
            try:
                if originals[p] is None:
                    p.unlink(missing_ok=True)
                else:
                    write_atomic(p, originals[p])
            except OSError:
                failed.append(str(p))
        if failed:
            raise OSError(f'Rollback failed for {failed}; backups: {mod_backup}') from error
        raise
    return result


def remove_outputs(conn, project_id: int, mod_id: str) -> list[Path]:
    """Удалить все файлы, записанные приложением для проекта.

    Удаляются ТОЛЬКО файлы из generated_outputs (созданные нами), каждый
    предварительно копируется в резервные копии. Нужна при смене режима
    записи (внутрь мода ↔ патч-мод), чтобы старый результат не остался
    в игре вторым слоем.
    """
    import shutil

    rows = _latest_outputs(conn, project_id)
    for check in verify_outputs(conn, project_id):
        if check.state == 'modified':
            raise ValueError(f'File edited outside the application: {check.path}')
    backup_root = backups_dir() / mod_id / "removed"
    removed: list[Path] = []
    for r in rows:
        p = Path(r["abs_path"])
        if p.exists():
            backup_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, backup_root / p.name)
            p.unlink()
            removed.append(p)
        # подчистить опустевшие каталоги (только внутри localization и патч-модов)
        parent = p.parent
        while parent.exists() and not any(parent.iterdir()):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    conn.execute(
        "DELETE FROM generated_outputs WHERE project_id=?", (project_id,)
    )
    conn.execute('DELETE FROM output_paths WHERE project_id=?', (project_id,))
    conn.commit()
    return removed


@dataclass
class OutputCheck:
    path: Path
    state: str  # ok | missing | modified


def verify_outputs(conn, project_id: int) -> list[OutputCheck]:
    """Сверить записанные файлы с базой: на месте ли, не правлены ли."""
    rows = _latest_outputs(conn, project_id)
    out = []
    for r in rows:
        p = Path(r["abs_path"])
        if not p.exists():
            out.append(OutputCheck(p, "missing"))
            continue
        actual = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        out.append(OutputCheck(p, "ok" if actual == r["file_hash"] else "modified"))
    return out
