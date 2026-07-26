"""Конвейер перевода: ваниль → память → API, защита кодов, глоссарий."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ck3loc.core import db
from ck3loc.core.glossary_seed import load_glossary, seed_glossary
from ck3loc.core.ops import load_project_context, rows_to_translate
from ck3loc.core.pipeline import estimate, translate_rows
from ck3loc.core.store import get_units, tm_store
from ck3loc.providers.base import ProviderError, ProviderInfo, TranslationProvider
from tests.test_scanner import make_fake_mod


class EchoProvider(TranslationProvider):
    """Фейковый провайдер: префикс «RU:» + сохранение маркеров."""

    info = ProviderInfo("echo", "Echo", needs_key=False, wave=1)
    batch_size = 3  # маленькие батчи, чтобы проверить пакетирование

    def __init__(self):
        super().__init__()
        self.calls = 0

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        self.calls += 1
        return ["RU: " + t for t in texts]


class EatMarksProvider(TranslationProvider):
    """Плохой провайдер: съедает защитные маркеры."""

    info = ProviderInfo("bad", "Bad", needs_key=False, wave=1)

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        return [t.replace("⟦", "").replace("⟧", "") for t in texts]


class FailingProvider(TranslationProvider):
    info = ProviderInfo("fail", "Fail", needs_key=False, wave=1)

    def translate_batch(self, *a, **kw):
        raise ProviderError("нет связи")


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        base = Path(self._td.name)
        os.environ["CK3LOC_DATA"] = str(base / "data")
        self.conn = db.connect()
        self.mod_dir = make_fake_mod(base / "workshop")
        self.ctx = load_project_context(
            self.conn, self.mod_dir.name, mod_dir=self.mod_dir
        )

    def tearDown(self):
        self.conn.close()
        os.environ.pop("CK3LOC_DATA", None)
        self._td.cleanup()


class TestScopes(PipelineTestCase):
    """Объём выгрузки: недостающие ≠ вся локализация."""

    def test_scopes_differ(self):
        from ck3loc.core.locparser import build_new_file
        from ck3loc.core.ops import (
            WHAT_ALL,
            WHAT_MISSING,
            WHAT_OUTDATED,
            counts_by_scope,
            load_project_context,
        )

        # автор мода сам перевёл часть строк
        native = self.mod_dir / "localization" / "russian" / "own_l_russian.yml"
        native.write_bytes(build_new_file("russian", [("greeting", "Привет")]))
        self.ctx = load_project_context(
            self.conn, self.mod_dir.name, mod_dir=self.mod_dir
        )

        counts = counts_by_scope(self.ctx)
        # авторский перевод не попадает в «недостающие», но попадает в «всё»
        self.assertGreater(counts[WHAT_ALL], counts[WHAT_MISSING])
        self.assertNotIn(
            "greeting",
            {r["key"] for r in rows_to_translate(self.ctx, WHAT_MISSING)},
        )
        self.assertIn(
            "greeting", {r["key"] for r in rows_to_translate(self.ctx, WHAT_ALL)}
        )
        self.assertEqual(
            counts[WHAT_OUTDATED],
            len(rows_to_translate(self.ctx, WHAT_OUTDATED)),
        )
        missing_keys = {r["key"] for r in rows_to_translate(self.ctx, WHAT_MISSING)}
        all_keys = {r["key"] for r in rows_to_translate(self.ctx, WHAT_ALL)}
        self.assertTrue(missing_keys < all_keys)


class TestPipeline(PipelineTestCase):
    def test_memory_then_api(self):
        rows = rows_to_translate(self.ctx, "missing")
        self.assertGreater(len(rows), 5)
        # положим одну строку в память переводов заранее
        tm_store(self.conn, "english", "russian", "Hello, world",
                 "Привет из памяти", approved=True)
        self.conn.commit()

        provider = EchoProvider()
        stats = translate_rows(self.ctx, rows, provider, vanilla_lookup={})
        self.assertEqual(stats.from_memory, 1)
        self.assertGreater(stats.from_api, 0)
        self.assertEqual(stats.translated + len(stats.failed), stats.total)
        self.assertGreater(provider.calls, 1)  # пакетирование работало

        units = get_units(self.conn, self.ctx.project_id)
        self.assertEqual(units["greeting"]["target_text"], "Привет из памяти")
        self.assertEqual(units["greeting"]["provider"], "memory")
        # у API-строк маркеры восстановлены в игровые коды
        icon_unit = units.get("icon")
        self.assertIsNotNone(icon_unit)
        self.assertIn("@epe_icon_epe_rule!", icon_unit["target_text"])
        self.assertNotIn("⟦", icon_unit["target_text"])

    def test_vanilla_priority(self):
        rows = [{"key": "greeting", "source": "Hello, world"}]
        stats = translate_rows(
            self.ctx, rows, EchoProvider(),
            vanilla_lookup={"Hello, world": "Официальный перевод"},
        )
        self.assertEqual(stats.from_vanilla, 1)
        units = get_units(self.conn, self.ctx.project_id)
        self.assertEqual(units["greeting"]["target_text"], "Официальный перевод")

    def test_broken_marks_rejected(self):
        rows = [r for r in rows_to_translate(self.ctx, "missing")
                if r["key"] == "icon"]
        stats = translate_rows(self.ctx, rows, EatMarksProvider(),
                               vanilla_lookup={})
        self.assertEqual(stats.from_api, 0)
        self.assertEqual(len(stats.failed), 1)
        units = get_units(self.conn, self.ctx.project_id)
        self.assertNotIn("icon", units)

    def test_provider_failure_does_not_crash(self):
        rows = rows_to_translate(self.ctx, "missing")[:4]
        stats = translate_rows(self.ctx, rows, FailingProvider(),
                               vanilla_lookup={})
        self.assertEqual(stats.from_api, 0)
        self.assertEqual(len(stats.failed), len(rows))
        self.assertIn("нет связи", stats.failed[0][1])

    def test_estimate(self):
        rows = rows_to_translate(self.ctx, "missing")
        tm_store(self.conn, "english", "russian", "Hello, world", "x")
        self.conn.commit()
        est = estimate(self.ctx, rows,
                       vanilla_lookup={"Alpha": "Альфа"})
        self.assertEqual(est.rows, len(rows))
        self.assertEqual(est.covered_by_vanilla, 1)
        self.assertEqual(est.covered_by_memory, 1)
        self.assertGreater(est.chars_to_api, 0)


class TestGlossary(PipelineTestCase):
    def test_seed_once(self):
        n = seed_glossary(self.conn)
        self.assertGreaterEqual(n, 40)
        self.assertEqual(seed_glossary(self.conn), 0)  # повторно не сеется
        terms = dict(load_glossary(self.conn))
        self.assertEqual(terms["Realm"], "Держава")
        self.assertEqual(terms["Holding"], "Владение")
        self.assertEqual(terms["County"], "Графство")

    def test_mod_level_overrides_global(self):
        seed_glossary(self.conn)
        self.conn.execute(
            """INSERT INTO glossary_terms (level, mod_id, source_term,
                   target_term, mode)
               VALUES ('mod', ?, 'Realm', 'Царство', 'required')""",
            (self.ctx.project["mod_id"],),
        )
        self.conn.commit()
        terms = dict(load_glossary(self.conn, self.ctx.project["mod_id"]))
        self.assertEqual(terms["Realm"], "Царство")


if __name__ == "__main__":
    unittest.main()
