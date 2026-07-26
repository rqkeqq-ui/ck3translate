"""JSONL-обмен с внешней LLM: экспорт файла-задания и строгий импорт.

Правила импорта: менять можно только target; id/key/source сверяются
с зарегистрированным экспортом; повреждённые коды блокируют строку;
изменившийся с момента экспорта источник — тоже.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .scanner import semantic_hash
from .tokens import protect, restore, validate_translation


def key_type(key: str) -> str:
    """Подсказка типа строки по ключу (эвристика, не жёсткое правило)."""
    low = key.lower()
    if low.endswith("_desc") or "_desc_" in low:
        return "desc"
    if low.startswith("rule_") or low.startswith("setting_") or "game_rule" in low:
        return "rule"
    if "tooltip" in low or low.endswith("_tt"):
        return "tooltip"
    if low.endswith("_name") or low.startswith(("dynn_", "nick_", "d_", "b_", "c_", "k_", "e_")):
        return "name"
    if "title" in low:
        return "title"
    return "text"


PROMPT_TEMPLATE = """Ты — переводчик модов Crusader Kings 3 с {source_lang} на {target_lang}.
Ниже приложен файл в формате JSONL: одна строка файла — один JSON-объект.

Правила (обязательные):
1. Заполни поле "target" переводом текста из поля "source". Больше НИЧЕГО не меняй:
   поля "id", "key", "source", "type", "tokens" должны остаться в точности как были.
2. Маркеры вида {mark_open}T1{mark_close}, {mark_open}T2{mark_close} — это защищённые игровые коды.
   Переноси их в перевод без изменений, в подходящее по смыслу место. Не переводить, не удалять, не добавлять свои.
3. Литеральную последовательность \\n (обратный слэш + n) сохраняй как есть.
4. Поле "type" подсказывает стиль: name/title — краткое название; desc — описание;
   rule — название правила игры; tooltip — текст подсказки.
5. Termины глоссария (если указан ниже) переводи строго по нему.
6. Верни ПОЛНЫЙ файл в том же формате JSONL: все строки, в том же порядке,
   по одному JSON-объекту на строку, без комментариев и пояснений.
{glossary_block}"""


@dataclass
class ExportResult:
    export_id: str
    path: Path
    prompt_path: Path
    unit_count: int


def export_jsonl(
    conn,
    project_id: int,
    rows: list[dict],
    out_path: Path,
    source_lang: str,
    target_lang: str,
    glossary: list[tuple[str, str]] | None = None,
) -> ExportResult:
    """rows: [{key, source}] — строки на перевод (уже отфильтрованные)."""
    export_id = uuid.uuid4().hex[:12]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    reg_rows = []
    for i, row in enumerate(rows, start=1):
        unit_id = f"u{i:04d}"
        prot = protect(row["source"])
        obj = {
            "id": unit_id,
            "key": row["key"],
            "type": key_type(row["key"]),
            "source": prot.text,
            "tokens": prot.mapping,
            "target": "",
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
        reg_rows.append(
            (export_id, unit_id, row["key"], row["source"],
             semantic_hash(row["source"]))
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    glossary_block = ""
    if glossary:
        terms = "\n".join(f"  {s} → {t}" for s, t in glossary)
        glossary_block = f"\nГлоссарий (обязательные соответствия):\n{terms}\n"
    prompt = PROMPT_TEMPLATE.format(
        source_lang=source_lang,
        target_lang=target_lang,
        mark_open="⟦",
        mark_close="⟧",
        glossary_block=glossary_block,
    )
    prompt_path = out_path.with_suffix(".prompt.txt")
    prompt_path.write_text(prompt, encoding="utf-8")

    conn.execute(
        """INSERT INTO exports (export_id, project_id, format, created_at,
                                unit_count)
           VALUES (?, ?, 'jsonl', ?, ?)""",
        (export_id, project_id, time.strftime("%Y-%m-%dT%H:%M:%S"), len(rows)),
    )
    conn.executemany(
        """INSERT INTO export_units (export_id, unit_id, key, source_text,
                                     source_hash)
           VALUES (?, ?, ?, ?, ?)""",
        reg_rows,
    )
    conn.commit()
    return ExportResult(export_id, out_path, prompt_path, len(rows))


@dataclass
class ImportedUnit:
    key: str
    target: str


@dataclass
class RejectedUnit:
    key: str
    unit_id: str
    reason: str


@dataclass
class ImportReport:
    accepted: list[ImportedUnit] = field(default_factory=list)
    rejected: list[RejectedUnit] = field(default_factory=list)
    fatal: str | None = None  # ошибка, блокирующая импорт целиком
    not_returned: int = 0     # строк экспорта, которых нет в файле

    @property
    def ok(self) -> bool:
        return self.fatal is None


def import_jsonl(
    conn,
    path: Path,
    current_source_values: dict[str, str],
    export_id: str | None = None,
) -> ImportReport:
    """Строгий импорт переведённого JSONL.

    current_source_values — текущие значения источника (свежий скан мода):
    если источник успел измениться после экспорта, строка отклоняется.
    """
    report = ImportReport()
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        report.fatal = f"файл не читается: {e}"
        return report

    objs: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            objs.append(json.loads(line))
        except json.JSONDecodeError as e:
            report.fatal = f"строка {lineno}: некорректный JSON ({e.msg})"
            return report
    if not objs:
        report.fatal = "файл пуст"
        return report

    # найти зарегистрированный экспорт: по параметру или по составу id
    ids = [str(o.get("id", "")) for o in objs]
    if len(set(ids)) != len(ids):
        report.fatal = "в файле есть повторяющиеся id"
        return report

    if export_id is None:
        row = conn.execute(
            """SELECT export_id FROM export_units WHERE unit_id=? AND key=?
               ORDER BY rowid DESC LIMIT 1""",
            (ids[0], str(objs[0].get("key", ""))),
        ).fetchone()
        if row is None:
            report.fatal = (
                "не найден экспорт, которому принадлежит файл — "
                "импортируйте файл, созданный этим приложением"
            )
            return report
        export_id = row["export_id"]

    reg = {
        r["unit_id"]: r
        for r in conn.execute(
            "SELECT * FROM export_units WHERE export_id=?", (export_id,)
        ).fetchall()
    }
    if not reg:
        report.fatal = f"экспорт {export_id} не найден в базе"
        return report
    # неполный файл — не ошибка: принимаем то, что вернулось, остальное
    # останется в работе (нейросети часто обрезают длинные ответы)
    report.not_returned = len(set(reg) - set(ids))

    for obj in objs:
        unit_id = str(obj.get("id", ""))
        key = str(obj.get("key", ""))
        entry = reg.get(unit_id)
        if entry is None:
            report.rejected.append(
                RejectedUnit(key, unit_id, "id не принадлежит этому экспорту")
            )
            continue
        if key != entry["key"]:
            report.rejected.append(
                RejectedUnit(key, unit_id,
                             f"ключ изменён (был {entry['key']})")
            )
            continue
        target_prot = str(obj.get("target", "") or "")
        if not target_prot.strip():
            report.rejected.append(RejectedUnit(key, unit_id, "перевод пуст"))
            continue
        tokens = obj.get("tokens") or {}
        if not isinstance(tokens, dict):
            report.rejected.append(RejectedUnit(key, unit_id, "испорчено поле tokens"))
            continue
        # источник успел обновиться?
        current = current_source_values.get(key)
        if current is None or semantic_hash(current) != entry["source_hash"]:
            report.rejected.append(
                RejectedUnit(
                    key, unit_id,
                    "исходный текст изменился после экспорта — "
                    "экспортируйте и переведите строку заново",
                )
            )
            continue
        target, problems = restore(target_prot, tokens)
        if problems:
            report.rejected.append(
                RejectedUnit(key, unit_id, "; ".join(problems))
            )
            continue
        errors = validate_translation(entry["source_text"], target)
        if errors:
            report.rejected.append(
                RejectedUnit(key, unit_id, "; ".join(errors))
            )
            continue
        report.accepted.append(ImportedUnit(key=key, target=target))
    return report
