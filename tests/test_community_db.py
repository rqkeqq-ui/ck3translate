"""Community Database: обнаружение, строгая валидация и безопасный импорт."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ck3loc.core import db
from ck3loc.core.community_db import (
    CommunityDatabaseError,
    clear_community_glossary,
    discover_community_database,
    import_community_glossary,
    load_community_database,
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def make_database(content: Path, item_id: str = "9000") -> Path:
    root = content / item_id
    write_json(
        root / "ck3loc-database.json",
        {
            "product": "ck3loc-community-database",
            "schema_version": 1,
            "database_version": "2026.08.01",
            "minimum_app_version": "0.1.0",
            "workshop_id": item_id,
        },
    )
    write_json(
        root / "glossary" / "glossaries.json",
        [
            {
                "source_lang": "english",
                "target_lang": "russian",
                "source_term": "Realm",
                "target_term": "Держава",
                "mode": "required",
            },
            {
                "source_lang": "english",
                "target_lang": "russian",
                "source_term": "County",
                "target_term": "Графство",
                "mode": "required",
            },
        ],
    )
    write_json(
        root / "registry" / "translation_mods.json",
        [
            {
                "source_mod_id": "1000",
                "provider_mod_id": "2000",
                "source_lang": "english",
                "target_lang": "russian",
            }
        ],
    )
    write_json(
        root / "registry" / "mod_rules.json",
        {
            "1000": {
                "source_language": "english",
                "exclude_globs": ["localization/english/debug/**"],
                "protected_key_prefixes": ["DEBUG_"],
            }
        },
    )
    return root


class CommunityDatabaseTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.content = self.base / "content" / "1158310"
        self.root = make_database(self.content)
        os.environ["CK3LOC_DATA"] = str(self.base / "data")

    def tearDown(self):
        os.environ.pop("CK3LOC_DATA", None)
        self._td.cleanup()

    def test_loads_all_sections(self):
        database = load_community_database(self.root, "9000")
        self.assertTrue(database.compatible)
        self.assertEqual(database.database_version, "2026.08.01")
        self.assertEqual(len(database.glossaries), 2)
        self.assertEqual(database.translations[0].provider_mod_id, "2000")
        self.assertEqual(database.mod_rules["1000"].source_language, "english")

    def test_discovers_marker_without_configured_id(self):
        result = discover_community_database(
            content_dirs=[self.content], preferred_id=""
        )
        self.assertEqual(result.state, "ready")
        self.assertEqual(result.workshop_id, "9000")

    def test_configured_id_does_not_accept_lookalike_item(self):
        result = discover_community_database(
            content_dirs=[self.content], preferred_id="123456"
        )
        self.assertEqual(result.state, "missing")
        self.assertIsNone(result.database)

    def test_rejects_wrong_schema_and_id_mismatch(self):
        marker = self.root / "ck3loc-database.json"
        value = json.loads(marker.read_text(encoding="utf-8"))
        value["schema_version"] = 999
        write_json(marker, value)
        with self.assertRaises(CommunityDatabaseError):
            load_community_database(self.root)

        value["schema_version"] = 1
        value["workshop_id"] = "9999"
        write_json(marker, value)
        with self.assertRaises(CommunityDatabaseError):
            load_community_database(self.root)

    def test_rejects_duplicate_terms(self):
        path = self.root / "glossary" / "glossaries.json"
        terms = json.loads(path.read_text(encoding="utf-8"))
        terms.append(dict(terms[0]))
        write_json(path, terms)
        with self.assertRaises(CommunityDatabaseError):
            load_community_database(self.root)

    def test_import_is_idempotent_and_user_term_wins(self):
        conn = db.connect()
        try:
            conn.execute(
                """INSERT INTO glossary_terms
                       (level, source_lang, target_lang, source_term,
                        target_term, mode, origin)
                   VALUES ('global', 'english', 'russian', 'Realm',
                           'Царство', 'required', 'user')"""
            )
            conn.commit()
            database = load_community_database(self.root)
            first = import_community_glossary(conn, database)
            self.assertEqual(first.added, 1)
            self.assertEqual(first.skipped_user, 1)
            second = import_community_glossary(conn, database)
            self.assertEqual(second.added, 0)
            self.assertEqual(second.updated, 0)
            realm = conn.execute(
                "SELECT target_term FROM glossary_terms WHERE source_term='Realm'"
            ).fetchone()
            self.assertEqual(realm["target_term"], "Царство")
        finally:
            conn.close()

    def test_unsubscribe_removes_community_copy_but_keeps_builtin(self):
        from ck3loc.core.glossary_seed import load_glossary, seed_glossary

        conn = db.connect()
        try:
            seed_glossary(conn)
            database = load_community_database(self.root)
            imported = import_community_glossary(conn, database)
            self.assertEqual(imported.added, 2)
            removed = clear_community_glossary(conn)
            self.assertEqual(removed, 2)
            terms = dict(load_glossary(conn))
            self.assertEqual(terms["Realm"], "Держава")
            origins = {
                r["origin"] for r in conn.execute(
                    "SELECT origin FROM glossary_terms WHERE source_term='Realm'"
                )
            }
            self.assertEqual(origins, {"builtin"})
        finally:
            conn.close()

    def test_old_database_is_migrated_without_losing_term(self):
        path = self.base / "old.sqlite3"
        import sqlite3

        old = sqlite3.connect(path)
        old.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        old.execute(
            """CREATE TABLE glossary_terms (
                   id INTEGER PRIMARY KEY, level TEXT, mod_id TEXT,
                   source_term TEXT, target_term TEXT, mode TEXT, note TEXT)"""
        )
        old.execute(
            "INSERT INTO glossary_terms VALUES (1, 'global', '', 'Mine', "
            "'Моё', 'required', '')"
        )
        old.commit()
        old.close()

        conn = db.connect(path)
        try:
            row = conn.execute(
                "SELECT source_lang, target_lang, origin, target_term "
                "FROM glossary_terms WHERE id=1"
            ).fetchone()
            self.assertEqual(tuple(row), ("english", "russian", "user", "Моё"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
