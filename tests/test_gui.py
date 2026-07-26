"""Тесты интерфейса: фильтры, редактор строк, глоссарий, темы.

Запускаются в offscreen-режиме Qt; если PySide6 не установлен — пропускаются.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

from tests.test_scanner import make_fake_mod

_app = None


def setUpModule():
    global _app
    if HAVE_QT:
        _app = QApplication.instance() or QApplication([])


@unittest.skipUnless(HAVE_QT, "PySide6 не установлен")
class GuiTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        base = Path(self._td.name)
        os.environ["CK3LOC_DATA"] = str(base / "данные")
        os.environ["CK3LOC_PDX_MOD_DIR"] = str(base / "Paradox Mods")
        self.mod_dir = make_fake_mod(base / "workshop")

    def tearDown(self):
        os.environ.pop("CK3LOC_DATA", None)
        os.environ.pop("CK3LOC_PDX_MOD_DIR", None)
        self._td.cleanup()


class TestTheme(GuiTestCase):
    def test_both_themes_render(self):
        from ck3loc.desktop.theme import palette, stylesheet

        for name in ("dark", "light"):
            css = stylesheet(name)
            self.assertIn("QPushButton", css)
            self.assertNotIn("{'", css)  # словарь не просочился в CSS
            self.assertIn(palette(name)["accent"], css)
        # надписи прозрачны — иначе тёмные прямоугольники на карточках
        self.assertIn("QLabel, QCheckBox { background: transparent; }",
                      stylesheet("dark"))


class TestLibraryPage(GuiTestCase):
    def _rows(self):
        from ck3loc.desktop.workers import ModRow

        return [
            ModRow("1", "Без перевода мод", 1, 0.0, "нет перевода", True,
                   "01.01.2026", 0, False),
            ModRow("2", "Неполный мод", 5, 50.0, "10 пропущено", True,
                   "02.01.2026", 1, True),
            ModRow("3", "Полный мод", 7, 100.0, "полный", True, "", 0, False),
            ModRow("4", "Без локализации", 0, None, "нет локализации", False,
                   "", 0, False),
        ]

    def test_tiles_and_filters(self):
        from ck3loc.desktop.library_page import LibraryPage

        page = LibraryPage("dark")
        page.set_rows(self._rows())
        self.assertEqual(page.tile_total.value_label.text(), "4")
        self.assertEqual(page.tile_noloc.value_label.text(), "1")
        self.assertEqual(page.tile_none.value_label.text(), "1")
        self.assertEqual(page.tile_partial.value_label.text(), "1")
        self.assertEqual(page.tile_full.value_label.text(), "1")
        self.assertEqual(page.tile_errors.value_label.text(), "1")
        self.assertEqual(page.table.rowCount(), 4)

        for filter_name, expected in [
            ("Без перевода", 1), ("Перевод неполный", 1), ("Перевод полный", 1),
            ("Мои проекты", 1), ("С ошибками", 1), ("Без локализации", 1),
            ("Все моды", 4),
        ]:
            page._set_filter(filter_name)
            self.assertEqual(page.table.rowCount(), expected, filter_name)

    def test_search(self):
        from ck3loc.desktop.library_page import LibraryPage

        page = LibraryPage("dark")
        page.set_rows(self._rows())
        page.search.setText("полный")
        self.assertEqual(page.table.rowCount(), 2)  # «Неполный» и «Полный»
        page.search.setText("3")
        self.assertEqual(page.table.rowCount(), 1)  # по ID
        page.search.setText("")
        self.assertEqual(page.table.rowCount(), 4)

    def test_theme_switch_updates_tiles(self):
        from ck3loc.desktop.library_page import LibraryPage
        from ck3loc.desktop.theme import palette

        page = LibraryPage("dark")
        page.set_rows(self._rows())
        page.apply_theme("light")
        self.assertIn(palette("light")["text"],
                      page.tile_total.value_label.styleSheet())


class TestModPage(GuiTestCase):
    def _page(self):
        from ck3loc.desktop.mod_page import ModPage

        page = ModPage("dark")
        self.assertTrue(page.load(self.mod_dir.name, mod_dir=self.mod_dir))
        return page

    def test_load_and_rows(self):
        page = self._page()
        self.assertIn("Test Mod", page.title.text())
        self.assertGreater(page.rows_table.rowCount(), 10)
        self.assertIn("Строки", page.tabs.tabText(1))
        self.assertIn("english", page.info.text())
        page.close_db()

    def test_row_filters(self):
        page = self._page()
        total = page.rows_table.rowCount()
        page.row_filter.setCurrentText("Не переведено")
        missing = page.rows_table.rowCount()
        self.assertGreater(missing, 0)
        page.row_filter.setCurrentText("Родной перевод мода")
        self.assertLess(page.rows_table.rowCount(), total)
        page.row_filter.setCurrentText("Все строки")
        self.assertEqual(page.rows_table.rowCount(), total)
        page.close_db()

    def test_row_search(self):
        page = self._page()
        page.row_search.setText("greeting")
        self.assertEqual(page.rows_table.rowCount(), 1)
        page.close_db()

    def test_edit_and_save_row(self):
        from ck3loc.core.status import REVIEWED
        from ck3loc.core.store import get_units

        page = self._page()
        page.row_search.setText("greeting")
        page.rows_table.selectRow(0)
        self.assertEqual(page.editor_key.text(), "greeting")
        self.assertEqual(page.col_now["text"].toPlainText(), "Hello, world")
        page.col_target["text"].setPlainText("Привет, мир")
        self.assertIn("в порядке", page.token_state.text())
        page.save_current_row()
        units = get_units(page.conn, page.ctx.project_id)
        self.assertEqual(units["greeting"]["target_text"], "Привет, мир")
        self.assertEqual(units["greeting"]["status"], REVIEWED)
        page.close_db()

    def test_editor_flags_broken_tokens(self):
        page = self._page()
        page.row_search.setText("icon")
        page.rows_table.selectRow(0)
        page.col_target["text"].setPlainText("перевод без иконки")
        self.assertIn("Игровые коды:", page.token_state.text())
        page.close_db()

    def test_write_plan_via_page(self):
        from ck3loc.core.writer import build_write_plan, verify_outputs

        page = self._page()
        page.row_search.setText("greeting")
        page.rows_table.selectRow(0)
        page.col_target["text"].setPlainText("Привет, мир")
        page.save_current_row()
        plan = build_write_plan(page.ctx.scan, page.ctx.project, page.ctx.units)
        self.assertEqual(plan.total_keys, 1)
        from ck3loc.core.writer import apply_write_plan

        apply_write_plan(page.conn, page.ctx.project_id, plan, page.ctx.scan,
                         page.ctx.units)
        checks = verify_outputs(page.conn, page.ctx.project_id)
        self.assertTrue(checks and all(c.state == "ok" for c in checks))
        page.close_db()


class TestGlossaryPage(GuiTestCase):
    def test_add_seed_delete(self):
        from ck3loc.desktop.glossary_page import GlossaryPage

        page = GlossaryPage("dark")
        page.seed()
        seeded = page.table.rowCount()
        self.assertGreaterEqual(seeded, 40)

        page.src.setText("Bookmark")
        page.dst.setText("Закладка")
        page.add_term()
        self.assertEqual(page.table.rowCount(), seeded + 1)

        page.search.setText("Bookmark")
        self.assertEqual(page.table.rowCount(), 1)
        page.table.selectRow(0)
        page.delete_selected()
        self.assertEqual(page.table.rowCount(), 0)
        page.search.setText("")
        self.assertEqual(page.table.rowCount(), seeded)
        page.close_db()


class TestMainWindow(GuiTestCase):
    def test_navigation_and_theme(self):
        from ck3loc.core import settings
        from ck3loc.desktop.main_window import MainWindow

        settings.set_value("scan_on_start", False)
        win = MainWindow()
        self.assertEqual(win.stack.currentIndex(), 0)
        win.go("glossary")
        self.assertEqual(win.stack.currentIndex(), 2)
        self.assertEqual(win.page_title.text(), "Глоссарий терминов")
        win.go("settings")
        self.assertEqual(win.stack.currentIndex(), 3)
        win.apply_theme("light")
        self.assertEqual(settings.get("theme"), "light")
        win.apply_theme("dark")
        win.add_note("тест уведомления")
        self.assertIn("тест уведомления", win.notifications[-1])
        self.assertIn("(1)", win.btn_notes.text())
        win.close()


if __name__ == "__main__":
    unittest.main()
