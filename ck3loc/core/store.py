"""Операции над хранилищем: моды, снимки, проекты, строки перевода."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .scanner import ModScan, localization_fingerprint


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------- моды ----------

def record_mod(
    conn: sqlite3.Connection,
    scan: ModScan,
    steam_time_updated: int = 0,
    workshop_title: str = "",
) -> None:
    conn.execute(
        """INSERT INTO mods (mod_id, name, workshop_title, mod_dir,
               descriptor_version, supported_version, steam_time_updated,
               installed, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
           ON CONFLICT(mod_id) DO UPDATE SET
               name=excluded.name,
               workshop_title=CASE WHEN excluded.workshop_title != ''
                   THEN excluded.workshop_title ELSE mods.workshop_title END,
               mod_dir=excluded.mod_dir,
               descriptor_version=excluded.descriptor_version,
               supported_version=excluded.supported_version,
               steam_time_updated=CASE WHEN excluded.steam_time_updated > 0
                   THEN excluded.steam_time_updated ELSE mods.steam_time_updated END,
               installed=1,
               last_seen_at=excluded.last_seen_at""",
        (
            scan.mod_id,
            scan.descriptor.name,
            workshop_title,
            str(scan.mod_dir),
            scan.descriptor.version,
            scan.descriptor.supported_version,
            steam_time_updated,
            _now(),
        ),
    )
    conn.commit()


def mark_missing_mods(conn: sqlite3.Connection, present_ids: set[str]) -> list[str]:
    """Отметить моды, папок которых больше нет. Данные не удаляются."""
    rows = conn.execute("SELECT mod_id FROM mods WHERE installed=1").fetchall()
    gone = [r["mod_id"] for r in rows if r["mod_id"] not in present_ids]
    for mod_id in gone:
        conn.execute("UPDATE mods SET installed=0 WHERE mod_id=?", (mod_id,))
    conn.commit()
    return gone


# ---------- снимки ----------

@dataclass
class SnapshotResult:
    snapshot_id: int
    is_new: bool
    fingerprint: str


def latest_snapshot(conn: sqlite3.Connection, mod_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM mod_snapshots WHERE mod_id=? ORDER BY id DESC LIMIT 1",
        (mod_id,),
    ).fetchone()


def take_snapshot(
    conn: sqlite3.Connection, scan: ModScan, steam_time_updated: int = 0
) -> SnapshotResult:
    """Снять снимок локализации; если она не изменилась — вернуть прежний."""
    fp = localization_fingerprint(scan)
    last = latest_snapshot(conn, scan.mod_id)
    if last is not None and last["loc_fingerprint"] == fp:
        return SnapshotResult(last["id"], False, fp)
    cur = conn.execute(
        """INSERT INTO mod_snapshots
               (mod_id, taken_at, loc_fingerprint, steam_time_updated,
                descriptor_version)
           VALUES (?, ?, ?, ?, ?)""",
        (scan.mod_id, _now(), fp, steam_time_updated, scan.descriptor.version),
    )
    snap_id = cur.lastrowid
    rows = []
    for lang, summary in scan.languages.items():
        for key, occ in summary.keys.items():
            rows.append(
                (
                    snap_id,
                    lang,
                    key,
                    occ.value,
                    occ.value_hash,
                    occ.rel_path,
                    1 if occ.replace_scope else 0,
                )
            )
    conn.executemany(
        """INSERT INTO snapshot_entries
               (snapshot_id, language, key, value, value_hash, rel_path,
                replace_scope)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return SnapshotResult(snap_id, True, fp)


def snapshot_language(
    conn: sqlite3.Connection, snapshot_id: int, language: str
) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """SELECT * FROM snapshot_entries
           WHERE snapshot_id=? AND language=?""",
        (snapshot_id, language),
    ).fetchall()
    return {r["key"]: r for r in rows}


@dataclass
class LangDiff:
    added: list[str]
    removed: list[str]
    changed: list[str]  # ключ есть в обоих, значение отличается

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_snapshots(
    conn: sqlite3.Connection,
    old_snapshot_id: int,
    new_snapshot_id: int,
    language: str,
) -> LangDiff:
    old = snapshot_language(conn, old_snapshot_id, language)
    new = snapshot_language(conn, new_snapshot_id, language)
    added = sorted(k for k in new if k not in old)
    removed = sorted(k for k in old if k not in new)
    changed = sorted(
        k
        for k in new
        if k in old and new[k]["value_hash"] != old[k]["value_hash"]
    )
    return LangDiff(added=added, removed=removed, changed=changed)


# ---------- проекты и строки ----------

def ensure_project(
    conn: sqlite3.Connection,
    mod_id: str,
    source_lang: str = "english",
    target_lang: str = "russian",
    write_mode: str = "in_mod",
) -> int:
    row = conn.execute(
        """SELECT id FROM translation_projects
           WHERE mod_id=? AND source_lang=? AND target_lang=?""",
        (mod_id, source_lang, target_lang),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO translation_projects
               (mod_id, source_lang, target_lang, write_mode, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (mod_id, source_lang, target_lang, write_mode, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_project(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM translation_projects WHERE id=?", (project_id,)
    ).fetchone()


def set_project_option(
    conn: sqlite3.Connection, project_id: int, field: str, value: str
) -> None:
    assert field in {"write_mode", "build_mode"}
    conn.execute(
        f"UPDATE translation_projects SET {field}=? WHERE id=?",
        (value, project_id),
    )
    conn.commit()


def upsert_unit(
    conn: sqlite3.Connection,
    project_id: int,
    key: str,
    source_text: str,
    source_hash: str,
    target_text: str,
    status: str,
    provider: str = "",
) -> None:
    conn.execute(
        """INSERT INTO translation_units
               (project_id, key, source_text, source_hash, target_text,
                status, provider, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(project_id, key) DO UPDATE SET
               source_text=excluded.source_text,
               source_hash=excluded.source_hash,
               target_text=excluded.target_text,
               status=excluded.status,
               provider=excluded.provider,
               updated_at=excluded.updated_at""",
        (project_id, key, source_text, source_hash, target_text, status,
         provider, _now()),
    )


def get_units(conn: sqlite3.Connection, project_id: int) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM translation_units WHERE project_id=?", (project_id,)
    ).fetchall()
    return {r["key"]: r for r in rows}


def set_unit_written_hash(
    conn: sqlite3.Connection, project_id: int, key: str, target_hash: str
) -> None:
    conn.execute(
        """UPDATE translation_units SET target_hash_written=?
           WHERE project_id=? AND key=?""",
        (target_hash, project_id, key),
    )


# ---------- память переводов ----------

def tm_lookup(
    conn: sqlite3.Connection, source_lang: str, target_lang: str, source_text: str
) -> str | None:
    row = conn.execute(
        """SELECT target_text FROM translation_memory
           WHERE source_lang=? AND target_lang=? AND source_text=?
           ORDER BY approved DESC, id DESC LIMIT 1""",
        (source_lang, target_lang, source_text),
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE translation_memory SET last_used_at=?
               WHERE source_lang=? AND target_lang=? AND source_text=?""",
            (_now(), source_lang, target_lang, source_text),
        )
    return row["target_text"] if row else None


def tm_store(
    conn: sqlite3.Connection,
    source_lang: str,
    target_lang: str,
    source_text: str,
    target_text: str,
    mod_id: str = "",
    key: str = "",
    approved: bool = False,
    provider: str = "",
) -> None:
    exists = conn.execute(
        """SELECT id FROM translation_memory
           WHERE source_lang=? AND target_lang=? AND source_text=?
             AND target_text=?""",
        (source_lang, target_lang, source_text, target_text),
    ).fetchone()
    if exists:
        return
    conn.execute(
        """INSERT INTO translation_memory
               (source_lang, target_lang, source_text, target_text, mod_id,
                key, approved, provider, created_at, last_used_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (source_lang, target_lang, source_text, target_text, mod_id, key,
         1 if approved else 0, provider, _now(), _now()),
    )
