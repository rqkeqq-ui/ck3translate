"""Workshop terminology import and bounded, relevant translation hints."""
from __future__ import annotations

import re
from pathlib import Path


def seed_glossary(conn) -> int:
    """Import terminology only from an installed, enabled Workshop database."""
    from . import settings
    from .community_db import discover_community_database, import_community_glossary

    cfg = settings.load()
    if not cfg.get("community_db_enabled", True):
        return 0
    steam = cfg.get("steam_path", "")
    result = discover_community_database(Path(steam) if steam else None)
    if result.state != "ready" or result.database is None:
        return 0
    return import_community_glossary(conn, result.database).added


def relevant_glossary(terms: list[tuple[str, str]], texts: list[str], limit: int = 80, max_chars: int = 6000) -> list[tuple[str, str]]:
    text = "\n".join(texts)
    result = []
    size = 0
    for source, target in sorted(terms, key=lambda item: (-len(item[0]), item[0])):
        if not re.search(r"(?<!\w)" + re.escape(source) + r"(?!\w)", text, re.IGNORECASE):
            continue
        length = len(source) + len(target) + 6
        if size + length > max_chars:
            continue
        result.append((source, target))
        size += length
        if len(result) >= limit:
            break
    return result


def load_glossary(
    conn,
    mod_id: str = "",
    source_lang: str = "english",
    target_lang: str = "russian",
) -> list[tuple[str, str]]:
    """Глоссарий для перевода: глобальный + уровня мода (мод переопределяет)."""
    terms: dict[str, str] = {}
    for r in conn.execute(
        "SELECT source_term, target_term FROM glossary_terms "
        "WHERE level='global' AND source_lang=? AND target_lang=? "
        "AND mode != 'forbidden' ORDER BY CASE origin WHEN 'user' THEN 2 WHEN 'builtin' THEN 0 ELSE 1 END, id",
        (source_lang, target_lang),
    ):
        terms[r["source_term"]] = r["target_term"]
    if mod_id:
        for r in conn.execute(
            "SELECT source_term, target_term FROM glossary_terms "
            "WHERE level='mod' AND mod_id=? AND source_lang=? AND target_lang=? "
            "AND mode != 'forbidden' ORDER BY CASE origin WHEN 'user' THEN 2 WHEN 'builtin' THEN 0 ELSE 1 END, id",
            (mod_id, source_lang, target_lang),
        ):
            terms[r["source_term"]] = r["target_term"]
    return sorted(terms.items())
