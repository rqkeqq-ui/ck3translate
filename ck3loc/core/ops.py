"""Операции уровня приложения: связывают сканер, базу, статусы и запись.

Используются и CLI, и GUI — вся логика здесь, интерфейсы только вызывают.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bundle import ImportReport
from .db import connect
from .scanner import ModScan, scan_mod, semantic_hash
from .status import (
    MACHINE,
    MISSING,
    NATIVE,
    STALE,
    RowState,
    project_rows,
)
from .steam import list_workshop_mod_dirs, read_workshop_acf, workshop_content_dirs
from .store import ensure_project, get_project, get_units, upsert_unit, tm_store
from .vanilla import game_languages


@dataclass
class ProjectContext:
    conn: object
    scan: ModScan
    project: dict
    project_id: int
    units: dict
    rows: list[RowState]

    @property
    def source_values(self) -> dict[str, str]:
        lang = self.project["source_lang"]
        summary = self.scan.languages.get(lang)
        return {k: o.value for k, o in summary.keys.items()} if summary else {}

    @property
    def native_values(self) -> dict[str, str]:
        lang = self.project["target_lang"]
        summary = self.scan.languages.get(lang)
        return {k: o.value for k, o in summary.keys.items()} if summary else {}


def find_mod_dir(mod_id: str, steam_path: Path | None = None) -> Path | None:
    content = workshop_content_dirs(steam_path)
    for d in list_workshop_mod_dirs(content):
        if d.name == mod_id:
            return d
    return None


def load_project_context(
    conn,
    mod_id: str,
    source_lang: str = "english",
    target_lang: str = "russian",
    steam_path: Path | None = None,
    mod_dir: Path | None = None,
) -> ProjectContext | None:
    if mod_dir is None:
        mod_dir = find_mod_dir(mod_id, steam_path)
    if mod_dir is None:
        return None
    scan = scan_mod(mod_dir, game_languages())
    # авто-подсказка источника: самый полный язык
    best = scan.best_source_language(source_lang)
    if best and best != source_lang and source_lang not in scan.languages:
        source_lang = best
    pid = ensure_project(conn, mod_id, source_lang, target_lang)
    project = dict(get_project(conn, pid))
    units = get_units(conn, pid)
    src = scan.languages.get(source_lang)
    native = scan.languages.get(target_lang)
    rows = project_rows(
        {k: o.value for k, o in src.keys.items()} if src else {},
        {k: dict(v) for k, v in units.items()},
        {k: o.value for k, o in native.keys.items()} if native else {},
    )
    return ProjectContext(conn, scan, project, pid, units, rows)


def rows_to_translate(ctx: ProjectContext, what: str = "missing") -> list[dict]:
    """Строки для экспорта/перевода: [{key, source}].

    what: missing — непереведённые; stale — устаревшие; all — оба набора.
    """
    wanted: set[str] = set()
    if what in ("missing", "all"):
        wanted |= {r.key for r in ctx.rows if r.status in (MISSING, NATIVE)}
        if what == "missing":
            # NATIVE (родной перевод есть) не включаем в «недостающие»
            wanted -= {r.key for r in ctx.rows if r.status == NATIVE}
    if what in ("stale", "all"):
        wanted |= {r.key for r in ctx.rows if r.status == STALE}
    src = ctx.source_values
    return [{"key": k, "source": src[k]} for k in sorted(wanted) if k in src]


def apply_import_report(
    ctx: ProjectContext, report: ImportReport, provider: str = "external_llm"
) -> int:
    """Принятые строки → база (статус «машинный») + память переводов."""
    src = ctx.source_values
    count = 0
    for item in report.accepted:
        source_text = src.get(item.key)
        if source_text is None:
            continue
        upsert_unit(
            ctx.conn, ctx.project_id, item.key, source_text,
            semantic_hash(source_text), item.target, MACHINE, provider,
        )
        tm_store(
            ctx.conn, ctx.project["source_lang"], ctx.project["target_lang"],
            source_text, item.target, ctx.project["mod_id"], item.key,
            approved=False, provider=provider,
        )
        count += 1
    ctx.conn.commit()
    return count


def acf_time_updated(mod_id: str) -> int:
    entry = read_workshop_acf().get(mod_id)
    return int(entry.time_updated) if entry and entry.time_updated else 0
