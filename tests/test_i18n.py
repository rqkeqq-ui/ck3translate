"""Локализация интерфейса: словари, подстановка, окно первого запуска."""

from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

from ck3loc.core.i18n import (
    UI_LANGUAGES,
    available_languages,
    ck3_language_for,
    lang_dir,
    set_language,
    tr,
)

_app = None


def setUpModule():
    global _app
    if HAVE_QT:
        _app = QApplication.instance() or QApplication([])


class TestDictionaries(unittest.TestCase):
    def tearDown(self):
        set_language("ru")

    def test_every_language_has_a_file(self):
        for code in UI_LANGUAGES:
            if code == "ru":
                continue  # русский — исходный текст
            path = lang_dir() / f"{code}.json"
            self.assertTrue(path.exists(), f"нет словаря {code}")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreater(len(data), 100, code)
            for key, value in data.items():
                self.assertTrue(value.strip(), f"{code}: пустой перевод {key}")

    def test_translation_applied(self):
        set_language("en")
        self.assertEqual(tr("Библиотека"), "Library")
        self.assertEqual(tr("Настройки"), "Settings")
        set_language("de")
        self.assertEqual(tr("Библиотека"), "Bibliothek")
        set_language("ko")
        self.assertEqual(tr("Глоссарий"), "용어집")

    def test_russian_is_identity(self):
        set_language("ru")
        self.assertEqual(tr("Библиотека"), "Библиотека")

    def test_unknown_string_falls_back(self):
        set_language("fr")
        self.assertEqual(tr("Такой строки нет"), "Такой строки нет")

    def test_missing_translation_falls_back_to_english(self):
        """Чего нет во французском, берётся из английского, а не из русского."""
        fr = json.loads((lang_dir() / "fr.json").read_text(encoding="utf-8"))
        en = json.loads((lang_dir() / "en.json").read_text(encoding="utf-8"))
        only_en = [k for k in en if k not in fr]
        set_language("fr")
        for key in only_en[:5]:
            self.assertEqual(tr(key), en[key])

    def test_ck3_language_mapping(self):
        self.assertEqual(ck3_language_for("ru"), "russian")
        self.assertEqual(ck3_language_for("zh"), "simp_chinese")
        self.assertEqual(ck3_language_for("ko"), "korean")

    def test_language_list(self):
        codes = [c for c, _n in available_languages()]
        self.assertEqual(
            sorted(codes), sorted(["ru", "en", "es", "fr", "de", "zh", "ko"])
        )


@unittest.skipUnless(HAVE_QT, "PySide6 не установлен")
class TestFirstRunDialog(unittest.TestCase):
    def tearDown(self):
        set_language("ru")

    def test_target_follows_ui_language(self):
        from ck3loc.desktop.first_run import FirstRunDialog

        dlg = FirstRunDialog(["english", "russian", "german", "korean"])
        dlg._select_ui("de")
        self.assertEqual(dlg.ui_language(), "de")
        self.assertEqual(dlg.target_language(), "german")
        dlg._select_ui("ko")
        self.assertEqual(dlg.target_language(), "korean")

    def test_manual_target_does_not_change_ui_language(self):
        from ck3loc.desktop.first_run import FirstRunDialog

        dlg = FirstRunDialog(["english", "russian", "german"])
        dlg._select_ui("en")
        dlg._select_target("russian")
        dlg._target_clicked(None)
        self.assertEqual(dlg.target_language(), "russian")
        self.assertEqual(dlg.ui_language(), "en")
        # и обратно: смена языка программы больше не трогает целевой
        dlg._select_ui("de")
        self.assertEqual(dlg.ui_language(), "de")
        self.assertEqual(dlg.target_language(), "russian")

    def test_dialog_texts_translated(self):
        from ck3loc.desktop.first_run import FirstRunDialog

        dlg = FirstRunDialog(["english", "russian"])
        dlg._select_ui("en")
        self.assertEqual(dlg.btn_ok.text(), "Continue")

    def test_source_language_default(self):
        from ck3loc.desktop.first_run import FirstRunDialog

        dlg = FirstRunDialog(["english", "russian"])
        dlg._select_ui("ru")
        self.assertEqual(dlg.source_language_default(), "english")
        dlg._select_ui("en")
        self.assertEqual(dlg.target_language(), "english")
        self.assertEqual(dlg.source_language_default(), "russian")


@unittest.skipUnless(HAVE_QT, "PySide6 не установлен")
class TestWidgetTreeTranslation(unittest.TestCase):
    def tearDown(self):
        set_language("ru")

    def test_tree_translation_and_switch_back(self):
        from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

        from ck3loc.desktop.translate_ui import translate_tree

        root = QWidget()
        layout = QVBoxLayout(root)
        btn = QPushButton("Настройки")
        layout.addWidget(btn)

        set_language("es")
        translate_tree(root)
        self.assertEqual(btn.text(), "Ajustes")
        # переключение языка работает и после перевода
        set_language("de")
        translate_tree(root)
        self.assertEqual(btn.text(), "Einstellungen")
        set_language("ru")
        translate_tree(root)
        self.assertEqual(btn.text(), "Настройки")


if __name__ == "__main__":
    unittest.main()
