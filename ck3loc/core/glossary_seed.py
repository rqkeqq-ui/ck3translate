"""Bundled CK3 terminology and bounded, relevant translation hints."""
from __future__ import annotations

import json
import re
from pathlib import Path


def seed_glossary(conn) -> int:
    terms = json.loads((Path(__file__).resolve().parent.parent / "data/glossary.json").read_text(encoding="utf-8"))
    added = 0
    for term in terms:
        rows = conn.execute(
            "SELECT id, origin FROM glossary_terms WHERE level='global' AND source_lang=? AND target_lang=? AND source_term=?",
            (term['source_lang'], term['target_lang'], term['source_term']),
        ).fetchall()
        if any(row['origin'] == 'user' for row in rows):
            continue
        builtin = next((row for row in rows if row['origin'] == 'builtin'), None)
        if builtin:
            conn.execute("UPDATE glossary_terms SET target_term=?, mode=?, note=? WHERE id=?",
                         (term['target_term'], term['mode'], term['note'], builtin['id']))
        elif not rows:
            conn.execute(
                "INSERT INTO glossary_terms (level, source_lang, target_lang, source_term, target_term, mode, note, origin) "
                "VALUES ('global', ?, ?, ?, ?, ?, ?, 'builtin')",
                tuple(term[k] for k in ('source_lang', 'target_lang', 'source_term', 'target_term', 'mode', 'note')),
            )
            added += 1
    conn.commit()
    return added


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
