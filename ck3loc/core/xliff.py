"""Экспорт/импорт XLIFF 2.1 (упрощённый профиль, совместимый с CAT-инструментами).

Игровые коды передаются как защищённые маркеры в тексте (тот же механизм,
что и в JSONL) — это переживает любой CAT-инструмент и любую LLM.
"""

from __future__ import annotations

import json
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .bundle import ImportReport, ImportedUnit, RejectedUnit
from .scanner import semantic_hash
from .tokens import protect, restore, validate_translation

NS = "urn:oasis:names:tc:xliff:document:2.0"

_LANG_CODES = {
    "english": "en", "french": "fr", "german": "de", "spanish": "es",
    "russian": "ru", "simp_chinese": "zh-Hans", "korean": "ko",
    "polish": "pl", "japanese": "ja",
}


def lang_code(lang: str) -> str:
    return _LANG_CODES.get(lang, lang)


@dataclass
class XliffExportResult:
    export_id: str
    path: Path
    unit_count: int


def export_xliff(
    conn,
    project_id: int,
    rows: list[dict],
    out_path: Path,
    source_lang: str,
    target_lang: str,
) -> XliffExportResult:
    export_id = uuid.uuid4().hex[:12]
    ET.register_namespace("", NS)
    root = ET.Element(
        f"{{{NS}}}xliff",
        {
            "version": "2.1",
            "srcLang": lang_code(source_lang),
            "trgLang": lang_code(target_lang),
        },
    )
    file_el = ET.SubElement(root, f"{{{NS}}}file", {"id": export_id})
    reg_rows = []
    for i, row in enumerate(rows, start=1):
        unit_id = f"u{i:04d}"
        prot = protect(row["source"])
        unit = ET.SubElement(
            file_el, f"{{{NS}}}unit", {"id": unit_id, "name": row["key"]}
        )
        notes = ET.SubElement(unit, f"{{{NS}}}notes")
        note = ET.SubElement(notes, f"{{{NS}}}note", {"category": "tokens"})
        note.text = json.dumps(prot.mapping, ensure_ascii=False)
        seg = ET.SubElement(unit, f"{{{NS}}}segment", {"state": "initial"})
        src = ET.SubElement(seg, f"{{{NS}}}source")
        src.text = prot.text
        ET.SubElement(seg, f"{{{NS}}}target")
        reg_rows.append(
            (export_id, unit_id, row["key"], row["source"],
             semantic_hash(row["source"]))
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)

    conn.execute(
        """INSERT INTO exports (export_id, project_id, format, created_at,
                                unit_count)
           VALUES (?, ?, 'xliff', ?, ?)""",
        (export_id, project_id, time.strftime("%Y-%m-%dT%H:%M:%S"), len(rows)),
    )
    conn.executemany(
        """INSERT INTO export_units (export_id, unit_id, key, source_text,
                                     source_hash)
           VALUES (?, ?, ?, ?, ?)""",
        reg_rows,
    )
    conn.commit()
    return XliffExportResult(export_id, out_path, len(rows))


def import_xliff(
    conn, path: Path, current_source_values: dict[str, str]
) -> ImportReport:
    report = ImportReport()
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as e:
        report.fatal = f"XLIFF не читается: {e}"
        return report
    root = tree.getroot()
    file_el = root.find(f"{{{NS}}}file")
    if file_el is None:
        report.fatal = "в XLIFF нет элемента file"
        return report
    export_id = file_el.get("id", "")
    reg = {
        r["unit_id"]: r
        for r in conn.execute(
            "SELECT * FROM export_units WHERE export_id=?", (export_id,)
        ).fetchall()
    }
    if not reg:
        report.fatal = f"экспорт {export_id} не найден в базе"
        return report

    seen: set[str] = set()
    for unit in file_el.findall(f"{{{NS}}}unit"):
        unit_id = unit.get("id", "")
        key = unit.get("name", "")
        seen.add(unit_id)
        entry = reg.get(unit_id)
        if entry is None or key != entry["key"]:
            report.rejected.append(
                RejectedUnit(key, unit_id, "id/ключ не соответствуют экспорту")
            )
            continue
        tokens: dict[str, str] = {}
        for note in unit.iter(f"{{{NS}}}note"):
            if note.get("category") == "tokens" and note.text:
                try:
                    tokens = json.loads(note.text)
                except json.JSONDecodeError:
                    tokens = {}
        seg = unit.find(f"{{{NS}}}segment")
        tgt = seg.find(f"{{{NS}}}target") if seg is not None else None
        target_prot = (tgt.text or "") if tgt is not None else ""
        if not target_prot.strip():
            report.rejected.append(RejectedUnit(key, unit_id, "перевод пуст"))
            continue
        current = current_source_values.get(key)
        if current is None or semantic_hash(current) != entry["source_hash"]:
            report.rejected.append(
                RejectedUnit(key, unit_id,
                             "исходный текст изменился после экспорта")
            )
            continue
        target, problems = restore(target_prot, tokens)
        if problems:
            report.rejected.append(RejectedUnit(key, unit_id, "; ".join(problems)))
            continue
        errors = validate_translation(entry["source_text"], target)
        if errors:
            report.rejected.append(RejectedUnit(key, unit_id, "; ".join(errors)))
            continue
        report.accepted.append(ImportedUnit(key=key, target=target))
    missing = set(reg) - seen
    if missing:
        report.fatal = (
            f"в файле не хватает {len(missing)} строк экспорта — верните полный файл"
        )
    return report
