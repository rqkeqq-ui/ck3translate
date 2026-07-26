"""Обнаружение модов-русификаторов: детект, выбор, влияние на недостающие."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ck3loc.core import db
from ck3loc.core.descriptor import render_descriptor
from ck3loc.core.external_translations import (
    find_provider_candidates,
    get_provider,
    provider_keys_for,
    provider_roles,
    providers_index,
    read_dependencies,
    save_candidates,
    set_manual_choice,
)
from ck3loc.core.locparser import build_new_file
from ck3loc.core.ops import WHAT_MISSING, load_project_context, rows_to_translate
from ck3loc.core.scanner import scan_mod
from ck3loc.core.status import EXTERNAL, MISSING
from ck3loc.core.store import record_mod, take_snapshot


def make_mod(root: Path, mod_id: str, name: str, lang: str,
             items: list[tuple[str, str]], dependencies: list[str] | None = None,
             replace: bool = False) -> Path:
    d = root / mod_id
    sub = d / "localization" / ("replace/" + lang if replace else lang)
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"{mod_id}_l_{lang}.yml").write_bytes(build_new_file(lang, items))
    text = render_descriptor(name, "1.0", "1.*")
    if dependencies:
        deps = "\n".join(f'\t"{x}"' for x in dependencies)
        text += "dependencies={\n" + deps + "\n}\n"
    (d / "descriptor.mod").write_text(text, encoding="utf-8")
    return d


class ExternalTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        os.environ["CK3LOC_DATA"] = str(self.base / "данные")
        self.conn = db.connect()
        self.workshop = self.base / "workshop"

        # оригинал: 100 английских строк
        self.orig = make_mod(
            self.workshop, "1000", "Great Mod", "english",
            [(f"gm_key_{i}", f"Text {i}") for i in range(100)],
        )
        # русификатор: переводит 90 из них, только русский, с зависимостью
        self.rus = make_mod(
            self.workshop, "2000", "Great Mod — Русификация", "russian",
            [(f"gm_key_{i}", f"Текст {i}") for i in range(90)],
            dependencies=["Great Mod"], replace=True,
        )
        # посторонний мод: случайно пересекается двумя ключами
        self.other = make_mod(
            self.workshop, "3000", "Unrelated", "russian",
            [("gm_key_0", "Другое"), ("gm_key_1", "Ещё")],
        )
        for d in (self.orig, self.rus, self.other):
            scan = scan_mod(d)
            record_mod(self.conn, scan)
            take_snapshot(self.conn, scan)

    def tearDown(self):
        self.conn.close()
        os.environ.pop("CK3LOC_DATA", None)
        self._td.cleanup()


class TestDetection(ExternalTestCase):
    def test_finds_provider(self):
        cands = find_provider_candidates(self.conn, "english", "russian")
        self.assertIn("1000", cands)
        best = cands["1000"][0]
        self.assertEqual(best.provider_id, "2000")
        self.assertEqual(best.covered_keys, 90)
        self.assertAlmostEqual(best.ratio, 0.9)
        self.assertTrue(best.by_dependency)
        self.assertTrue(best.by_name)
        self.assertEqual(best.confidence, "высокая")

    def test_random_overlap_below_threshold_ignored(self):
        cands = find_provider_candidates(self.conn, "english", "russian")
        ids = [c.provider_id for c in cands.get("1000", [])]
        self.assertNotIn("3000", ids)  # 2 ключа — ниже порога

    def test_thresholds_respected(self):
        cands = find_provider_candidates(
            self.conn, "english", "russian", min_ratio=0.95, min_keys=30
        )
        # 90% < 95%, но зависимость в descriptor всё равно подтверждает связь
        self.assertIn("1000", cands)
        cands2 = find_provider_candidates(
            self.conn, "english", "russian", min_keys=200
        )
        self.assertNotIn("1000", cands2)

    def test_dependencies_parsed(self):
        self.assertEqual(read_dependencies(self.rus), ["Great Mod"])
        self.assertEqual(read_dependencies(self.orig), [])

    def test_save_and_index(self):
        cands = find_provider_candidates(self.conn, "english", "russian")
        save_candidates(self.conn, "russian", cands)
        self.assertEqual(providers_index(self.conn, "russian").get("1000"), "2000")
        self.assertEqual(provider_roles(self.conn, "russian").get("2000"), ["1000"])
        self.assertEqual(len(provider_keys_for(self.conn, "1000", "russian")), 90)

    def test_manual_choice_survives_rescan(self):
        cands = find_provider_candidates(self.conn, "english", "russian")
        save_candidates(self.conn, "russian", cands)
        set_manual_choice(self.conn, "1000", "russian", "")  # не учитывать
        save_candidates(self.conn, "russian", cands)         # повторный скан
        self.assertIsNone(get_provider(self.conn, "1000", "russian"))
        self.assertEqual(provider_keys_for(self.conn, "1000", "russian"), set())


class TestEffectOnTranslation(ExternalTestCase):
    def test_covered_keys_are_not_missing(self):
        cands = find_provider_candidates(self.conn, "english", "russian")
        save_candidates(self.conn, "russian", cands)
        ctx = load_project_context(self.conn, "1000", mod_dir=self.orig)
        statuses = {}
        for r in ctx.rows:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        self.assertEqual(statuses.get(EXTERNAL), 90)
        self.assertEqual(statuses.get(MISSING), 10)
        missing = rows_to_translate(ctx, WHAT_MISSING)
        self.assertEqual(len(missing), 10)
        self.assertIsNotNone(ctx.provider)

    def test_without_provider_all_missing(self):
        ctx = load_project_context(self.conn, "1000", mod_dir=self.orig)
        self.assertEqual(len(rows_to_translate(ctx, WHAT_MISSING)), 100)
        self.assertIsNone(ctx.provider)

    def test_write_plan_uses_unique_filenames(self):
        """Иначе одноимённый файл русификатора перекроет наш целиком."""
        from ck3loc.core.scanner import semantic_hash
        from ck3loc.core.status import MACHINE
        from ck3loc.core.store import get_project, get_units, upsert_unit
        from ck3loc.core.writer import build_write_plan

        cands = find_provider_candidates(self.conn, "english", "russian")
        save_candidates(self.conn, "russian", cands)
        ctx = load_project_context(self.conn, "1000", mod_dir=self.orig)
        upsert_unit(self.conn, ctx.project_id, "gm_key_95", "Text 95",
                    semantic_hash("Text 95"), "Текст 95", MACHINE, "t")
        self.conn.commit()
        units = get_units(self.conn, ctx.project_id)
        project = dict(get_project(self.conn, ctx.project_id))
        plan = build_write_plan(ctx.scan, project, units,
                                has_external_provider=True)
        names = [f.abs_path.name for f in plan.files]
        self.assertTrue(all(n.startswith("zz_ck3loc_") for n in names), names)
        plain = build_write_plan(ctx.scan, project, units,
                                 has_external_provider=False)
        self.assertFalse(plain.files[0].abs_path.name.startswith("zz_ck3loc_"))


if __name__ == "__main__":
    unittest.main()
