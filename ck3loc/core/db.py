"""SQLite-хранилище приложения.

Одна папка данных в профиле пользователя; переопределяется переменной
окружения CK3LOC_DATA (это же используют тесты).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS mods (
    mod_id TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    workshop_title TEXT DEFAULT '',
    mod_dir TEXT DEFAULT '',
    descriptor_version TEXT DEFAULT '',
    supported_version TEXT DEFAULT '',
    steam_time_updated INTEGER DEFAULT 0,
    installed INTEGER DEFAULT 1,
    last_seen_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS mod_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    loc_fingerprint TEXT NOT NULL,
    steam_time_updated INTEGER DEFAULT 0,
    descriptor_version TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_snapshots_mod ON mod_snapshots(mod_id, id);
CREATE TABLE IF NOT EXISTS snapshot_entries (
    snapshot_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    replace_scope INTEGER DEFAULT 0,
    PRIMARY KEY (snapshot_id, language, key)
);
CREATE TABLE IF NOT EXISTS translation_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    write_mode TEXT DEFAULT 'in_mod',      -- in_mod | patch_mod
    build_mode TEXT DEFAULT 'auto',        -- auto | full | delta
    created_at TEXT DEFAULT '',
    UNIQUE (mod_id, source_lang, target_lang)
);
CREATE TABLE IF NOT EXISTS translation_units (
    project_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    source_text TEXT DEFAULT '',
    source_hash TEXT DEFAULT '',           -- источник на момент перевода
    target_text TEXT DEFAULT '',
    target_hash_written TEXT DEFAULT '',   -- хеш значения при последней записи на диск
    status TEXT DEFAULT 'untranslated',    -- untranslated|machine|reviewed|approved
    provider TEXT DEFAULT '',
    updated_at TEXT DEFAULT '',
    PRIMARY KEY (project_id, key)
);
CREATE TABLE IF NOT EXISTS translation_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    mod_id TEXT DEFAULT '',
    key TEXT DEFAULT '',
    approved INTEGER DEFAULT 0,
    provider TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    last_used_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tm_lookup
    ON translation_memory(source_lang, target_lang, source_text);
CREATE TABLE IF NOT EXISTS glossary_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT DEFAULT 'global',           -- global | mod | project
    mod_id TEXT DEFAULT '',
    source_lang TEXT DEFAULT 'english',
    target_lang TEXT DEFAULT 'russian',
    source_term TEXT NOT NULL,
    target_term TEXT DEFAULT '',
    mode TEXT DEFAULT 'preferred',         -- required | preferred | forbidden
    note TEXT DEFAULT '',
    origin TEXT DEFAULT 'user'             -- user | builtin | community:<id>
);
CREATE TABLE IF NOT EXISTS generated_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    abs_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    write_mode TEXT NOT NULL,
    written_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outputs_project ON generated_outputs(project_id);
CREATE TABLE IF NOT EXISTS translation_providers (
    mod_id TEXT NOT NULL,              -- мод, который переводят
    target_lang TEXT NOT NULL,
    provider_mod_id TEXT NOT NULL,     -- мод-русификатор ('' — не учитывать)
    covered_keys INTEGER DEFAULT 0,
    source_keys INTEGER DEFAULT 0,
    chosen_manually INTEGER DEFAULT 0, -- 1, если выбор сделал пользователь
    PRIMARY KEY (mod_id, target_lang)
);
CREATE TABLE IF NOT EXISTS exports (
    export_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    format TEXT NOT NULL,
    created_at TEXT NOT NULL,
    unit_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS export_units (
    export_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    key TEXT NOT NULL,
    source_text TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY (export_id, unit_id)
);
CREATE TABLE IF NOT EXISTS translation_jobs (
    id TEXT PRIMARY KEY, project_id INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft', provider TEXT DEFAULT '',
    model TEXT DEFAULT '', options TEXT DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_results (
    job_id TEXT NOT NULL, key TEXT NOT NULL, source_text TEXT NOT NULL,
    baseline TEXT NOT NULL, target_text TEXT, provenance TEXT DEFAULT '{}',
    error TEXT DEFAULT '', applied INTEGER DEFAULT 0,
    PRIMARY KEY(job_id, key)
);
CREATE TABLE IF NOT EXISTS translation_actions (
    id TEXT PRIMARY KEY, project_id INTEGER NOT NULL, kind TEXT NOT NULL,
    created_at TEXT NOT NULL, undone INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS action_rows (
    action_id TEXT NOT NULL, key TEXT NOT NULL, before_json TEXT NOT NULL,
    after_json TEXT NOT NULL, memory_id INTEGER, suppression_json TEXT DEFAULT '[]',
    undone INTEGER DEFAULT 0, PRIMARY KEY(action_id, key)
);
CREATE TABLE IF NOT EXISTS memory_suppressions (
    project_id INTEGER NOT NULL, key TEXT NOT NULL, memory_id INTEGER NOT NULL,
    PRIMARY KEY(project_id, key, memory_id)
);
CREATE TABLE IF NOT EXISTS export_parts (
    export_id TEXT NOT NULL, part INTEGER NOT NULL, path TEXT NOT NULL,
    keys_json TEXT NOT NULL, PRIMARY KEY(export_id, part)
);
CREATE TABLE IF NOT EXISTS export_returns (
    export_id TEXT NOT NULL, key TEXT NOT NULL, target_text TEXT NOT NULL,
    PRIMARY KEY(export_id, key)
);
CREATE TABLE IF NOT EXISTS export_packages (
    package TEXT NOT NULL, archive INTEGER NOT NULL, export_id TEXT NOT NULL,
    PRIMARY KEY(package, export_id)
);
CREATE TABLE IF NOT EXISTS output_paths (
    project_id INTEGER NOT NULL, logical_path TEXT NOT NULL, abs_path TEXT NOT NULL,
    PRIMARY KEY(project_id, logical_path), UNIQUE(abs_path)
);
"""


def _ensure_column(
    conn: sqlite3.Connection, table: str, name: str, declaration: str
) -> None:
    """Добавить колонку старой базе без потери пользовательских данных."""
    columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def _migrate(conn: sqlite3.Connection) -> None:
    # v3: язык и происхождение терминов нужны для подписных глоссариев.
    _ensure_column(
        conn, "glossary_terms", "source_lang", "TEXT DEFAULT 'english'"
    )
    _ensure_column(
        conn, "glossary_terms", "target_lang", "TEXT DEFAULT 'russian'"
    )
    _ensure_column(conn, "glossary_terms", "origin", "TEXT DEFAULT 'user'")
    for table in ("translation_units", "translation_memory"):
        _ensure_column(conn, table, "origin_kind", "TEXT DEFAULT 'unknown'")
        _ensure_column(conn, table, "model", "TEXT DEFAULT ''")
        _ensure_column(conn, table, "method", "TEXT DEFAULT 'direct'")
        _ensure_column(conn, table, "job_id", "TEXT DEFAULT ''")
        conn.execute(f"""UPDATE {table} SET origin_kind=CASE
            WHEN provider IN ('google','deepl','yandex') THEN 'service'
            WHEN provider IN ('openai','claude','chatgpt','external_llm') THEN 'llm'
            WHEN provider IN ('manual','vanilla','native','external_mod') THEN provider
            ELSE 'unknown' END WHERE origin_kind='unknown'""")
    _ensure_column(conn, "export_units", "baseline", "TEXT DEFAULT ''")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_glossary_pair_term
        ON glossary_terms(source_lang,target_lang,source_term,level,mod_id)""")
    conn.execute(
        """INSERT INTO meta(key, value) VALUES ('schema_version', ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (str(SCHEMA_VERSION),),
    )


def data_dir() -> Path:
    override = os.environ.get("CK3LOC_DATA")
    if override:
        d = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        d = Path(base) / "ck3loc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backups_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or (data_dir() / "ck3loc.sqlite3")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    has_meta = conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
    version = None
    if has_meta:
        version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if version and int(version[0]) < SCHEMA_VERSION:
            backup_path = path.with_name(path.name + f'.v{version[0]}.bak')
            if not backup_path.exists():
                backup = sqlite3.connect(str(backup_path))
                try:
                    conn.backup(backup)
                finally:
                    backup.close()
    conn.executescript(SCHEMA)
    # Миграция проходит по всем строкам памяти переводов — на больших базах
    # это доли секунды на каждое подключение, поэтому только при смене версии.
    if not version or int(version[0]) < SCHEMA_VERSION:
        _migrate(conn)
    conn.commit()
    return conn
