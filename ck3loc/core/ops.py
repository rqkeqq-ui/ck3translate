"""Операции уровня приложения: связывают сканер, базу, статусы и запись.

Используются и CLI, и GUI — вся логика здесь, интерфейсы только вызывают.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bundle import ImportReport
from .db import connect
from .external_translations import get_provider, provider_keys_for
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
    # мод-русификатор, покрывающий этот мод (строка translation_providers)
    provider: object | None = None

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
    from .mod_library import discover_mods

    for mod in discover_mods(steam_path).mods:
        if mod.mod_id == mod_id:
            return mod.path
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
    from . import settings
    from .community_db import discover_community_database

    cfg = settings.load()
    community_result = discover_community_database(
        steam_path, enabled=bool(cfg.get("community_db_enabled", True))
    )
    community = community_result.database
    if community_result.state == "ready" and community is not None:
        from .community_db import import_community_glossary

        import_community_glossary(conn, community)
    rule = community.mod_rules.get(mod_id) if community else None
    scan = scan_mod(mod_dir, game_languages(), rule=rule, mod_id=mod_id)
    # авто-подсказка источника: самый полный язык
    best = (
        scan.source_language_hint
        if scan.source_language_hint in scan.languages
        else scan.best_source_language(source_lang)
    )
    if scan.source_language_hint in scan.languages:
        source_lang = scan.source_language_hint
    elif best and best != source_lang and source_lang not in scan.languages:
        source_lang = best
    pid = ensure_project(conn, mod_id, source_lang, target_lang)
    project = dict(get_project(conn, pid))
    units = get_units(conn, pid)
    src = scan.languages.get(source_lang)
    native = scan.languages.get(target_lang)
    external = provider_keys_for(conn, mod_id, target_lang)
    rows = project_rows(
        {k: o.value for k, o in src.keys.items()} if src else {},
        {k: dict(v) for k, v in units.items()},
        {k: o.value for k, o in native.keys.items()} if native else {},
        external_keys=external,
    )
    ctx = ProjectContext(conn, scan, project, pid, units, rows)
    ctx.provider = get_provider(conn, mod_id, target_lang)
    return ctx


# наборы строк для выгрузки и перевода
WHAT_MISSING = "missing"      # только непереведённые
WHAT_STALE = "stale"          # только устаревшие
WHAT_OUTDATED = "outdated"    # непереведённые + устаревшие (обычный выбор)
WHAT_ALL = "all"              # плюс строки, переведённые самим модом


def rows_to_translate(ctx: ProjectContext, what: str = WHAT_OUTDATED) -> list[dict]:
    """Строки для выгрузки/перевода: [{key, source}].

    Строки, покрытые сторонним модом-русификатором, в «недостающие»
    не попадают — их уже переводить не нужно.
    """
    statuses: set[str] = set()
    if what in (WHAT_MISSING, WHAT_OUTDATED, WHAT_ALL):
        statuses.add(MISSING)
    if what in (WHAT_STALE, WHAT_OUTDATED, WHAT_ALL):
        statuses.add(STALE)
    if what == WHAT_ALL:
        # полная переработка: берём и то, что перевёл сам автор мода
        statuses.add(NATIVE)
    wanted = {r.key for r in ctx.rows if r.status in statuses}
    src = ctx.source_values
    return [{"key": k, "source": src[k]} for k in sorted(wanted) if k in src]


def counts_by_scope(ctx: ProjectContext) -> dict[str, int]:
    """Сколько строк в каждом наборе — для сметы перед выгрузкой."""
    return {
        what: len(rows_to_translate(ctx, what))
        for what in (WHAT_MISSING, WHAT_STALE, WHAT_OUTDATED, WHAT_ALL)
    }


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
