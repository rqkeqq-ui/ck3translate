"""Запись перевода: режим «внутрь мода» (по умолчанию) и патч-мод.

Железные правила: файлы автора никогда не изменяются; всё записанное
регистрируется в базе и восстановимо; запись атомарна с бэкапом.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
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
    override = os.environ.get("CK3LOC_PDX_MOD_DIR")
    if override:
        return Path(override)
    return (
        Path.home() / "Documents" / "Paradox Interactive"
        / "Crusader Kings III" / "mod"
    )


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

    # delta: не пишем то, что в родном переводе уже точно так же
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
        fname = _mirror_name(occ.rel_path, source_lang, target_lang)
        by_file.setdefault(fname, []).append((key, value))

    for fname, items in sorted(by_file.items()):
        target_path = lang_dir / fname
        # никогда не трогаем чужой файл: если файл существует и он не наш —
        # берём отличающееся имя с префиксом
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


def _guard_author_files(plan: WritePlan, scan: ModScan, conn, project_id: int) -> None:
    """Железное правило: не перезаписывать файлы автора.

    Файл можно перезаписать, только если он создан нами (есть в
    generated_outputs) или не существует.
    """
    ours = {
        r["abs_path"]
        for r in conn.execute(
            "SELECT abs_path FROM generated_outputs WHERE project_id=?",
            (project_id,),
        ).fetchall()
    }
    for pf in plan.files:
        if pf.kind in ("descriptor", "dot_mod", "manifest"):
            continue
        if pf.abs_path.exists() and str(pf.abs_path) not in ours:
            # чужой файл — сдвигаем имя
            pf.abs_path = pf.abs_path.with_name("zz_ck3loc_" + pf.abs_path.name)


def apply_write_plan(
    conn, project_id: int, plan: WritePlan, scan: ModScan, units: dict
) -> WriteResult:
    result = WriteResult()
    _guard_author_files(plan, scan, conn, project_id)
    mod_backup = backups_dir() / scan.mod_id
    for pf in plan.files:
        backup = write_atomic(pf.abs_path, pf.data, backup_dir=mod_backup)
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
    conn.commit()
    return result


def remove_outputs(conn, project_id: int, mod_id: str) -> list[Path]:
    """Удалить все файлы, записанные приложением для проекта.

    Удаляются ТОЛЬКО файлы из generated_outputs (созданные нами), каждый
    предварительно копируется в резервные копии. Нужна при смене режима
    записи (внутрь мода ↔ патч-мод), чтобы старый результат не остался
    в игре вторым слоем.
    """
    import shutil

    rows = conn.execute(
        "SELECT DISTINCT abs_path FROM generated_outputs WHERE project_id=?",
        (project_id,),
    ).fetchall()
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
    conn.commit()
    return removed


@dataclass
class OutputCheck:
    path: Path
    state: str  # ok | missing | modified


def verify_outputs(conn, project_id: int) -> list[OutputCheck]:
    """Сверить записанные файлы с базой: на месте ли, не правлены ли."""
    rows = conn.execute(
        """SELECT abs_path, file_hash, MAX(written_at)
           FROM generated_outputs WHERE project_id=? GROUP BY abs_path""",
        (project_id,),
    ).fetchall()
    out = []
    for r in rows:
        p = Path(r["abs_path"])
        if not p.exists():
            out.append(OutputCheck(p, "missing"))
            continue
        actual = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        out.append(OutputCheck(p, "ok" if actual == r["file_hash"] else "modified"))
    return out
