"""Ворота этапа 3: снимки, diff версий, автомат статусов."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ck3loc.core import db
from ck3loc.core.scanner import scan_mod, semantic_hash
from ck3loc.core.status import (
    CONFLICT,
    EDITED_OUTSIDE,
    EXTRA,
    MACHINE,
    MISSING,
    NATIVE,
    ORPHAN,
    REVIEWED,
    STALE,
    compute_row_state,
)
from ck3loc.core.store import (
    diff_snapshots,
    ensure_project,
    get_units,
    take_snapshot,
    upsert_unit,
)
from tests.test_scanner import make_fake_mod


class SnapshotTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["CK3LOC_DATA"] = str(Path(self._td.name) / "данные")
        self.conn = db.connect()
        self.mod_dir = make_fake_mod(Path(self._td.name) / "workshop")

    def tearDown(self):
        self.conn.close()
        os.environ.pop("CK3LOC_DATA", None)
        self._td.cleanup()


class TestSnapshots(SnapshotTestCase):
    def test_snapshot_dedup_and_diff(self):
        scan1 = scan_mod(self.mod_dir)
        s1 = take_snapshot(self.conn, scan1)
        self.assertTrue(s1.is_new)

        # повторный снимок без изменений — не создаётся
        s1b = take_snapshot(self.conn, scan_mod(self.mod_dir))
        self.assertFalse(s1b.is_new)
        self.assertEqual(s1b.snapshot_id, s1.snapshot_id)

        # комментарий/пустая строка не создают новый снимок
        f = self.mod_dir / "localization" / "english" / "lf_l_english.yml"
        original = f.read_bytes()
        f.write_bytes(original + b"# just a comment\n")
        s1c = take_snapshot(self.conn, scan_mod(self.mod_dir))
        self.assertFalse(s1c.is_new)

        # реальные изменения: добавить, изменить, удалить
        f.write_bytes(
            b'l_english:\n key_a: "Alpha CHANGED"\n key_new: "Brand new"\n'
        )  # key_b удалён
        s2 = take_snapshot(self.conn, scan_mod(self.mod_dir))
        self.assertTrue(s2.is_new)

        diff = diff_snapshots(self.conn, s1.snapshot_id, s2.snapshot_id, "english")
        self.assertEqual(diff.added, ["key_new"])
        self.assertEqual(diff.removed, ["key_b"])
        self.assertEqual(diff.changed, ["key_a"])


class TestStatusMachine(unittest.TestCase):
    """Полный перебор таблицы состояний из раздела 7 спецификации."""

    def unit(self, source, target, status=MACHINE, written_hash=""):
        return {
            "source_text": source,
            "source_hash": semantic_hash(source) if source else "",
            "target_text": target,
            "target_hash_written": written_hash,
            "status": status,
        }

    def test_missing(self):
        st = compute_row_state("k", "Hello", None)
        self.assertEqual(st.status, MISSING)

    def test_native_untracked(self):
        st = compute_row_state("k", "Hello", None, native_target_value="Привет")
        self.assertEqual(st.status, NATIVE)

    def test_current_machine_and_reviewed(self):
        u = self.unit("Hello", "Привет")
        self.assertEqual(compute_row_state("k", "Hello", u).status, MACHINE)
        u = self.unit("Hello", "Привет", status=REVIEWED)
        self.assertEqual(compute_row_state("k", "Hello", u).status, REVIEWED)

    def test_stale_when_source_changed(self):
        u = self.unit("Hello", "Привет", status=REVIEWED)
        st = compute_row_state("k", "Hello, world", u)
        self.assertEqual(st.status, STALE)
        self.assertEqual(st.baseline_source, "Hello")

    def test_conflict_source_and_target_changed(self):
        u = self.unit(
            "Hello", "Привет", written_hash=semantic_hash("Привет")
        )
        st = compute_row_state(
            "k", "Hello, world", u, written_target_value="Привет (правлено руками)"
        )
        self.assertEqual(st.status, CONFLICT)

    def test_edited_outside_only(self):
        u = self.unit("Hello", "Привет", written_hash=semantic_hash("Привет"))
        st = compute_row_state(
            "k", "Hello", u, written_target_value="Привет!!!"
        )
        self.assertEqual(st.status, EDITED_OUTSIDE)

    def test_orphan(self):
        u = self.unit("Hello", "Привет")
        st = compute_row_state("k", None, u)
        self.assertEqual(st.status, ORPHAN)

    def test_extra_only_in_target(self):
        st = compute_row_state("k", None, None, native_target_value="Только рус")
        self.assertEqual(st.status, EXTRA)

    def test_same_as_source_flag(self):
        u = self.unit("Enabled", "Enabled")
        st = compute_row_state("k", "Enabled", u)
        self.assertTrue(st.same_as_source)


class TestProjectUnits(SnapshotTestCase):
    def test_project_roundtrip(self):
        scan = scan_mod(self.mod_dir)
        take_snapshot(self.conn, scan)
        pid = ensure_project(self.conn, scan.mod_id)
        upsert_unit(
            self.conn, pid, "greeting", "Hello, world",
            semantic_hash("Hello, world"), "Привет, мир", MACHINE, "test",
        )
        self.conn.commit()
        units = get_units(self.conn, pid)
        self.assertIn("greeting", units)
        self.assertEqual(units["greeting"]["target_text"], "Привет, мир")
        # ensure_project идемпотентен
        self.assertEqual(ensure_project(self.conn, scan.mod_id), pid)


if __name__ == "__main__":
    unittest.main()
