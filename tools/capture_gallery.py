"""Render actual Qt widgets with isolated, synthetic demonstration data."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main() -> None:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QFont, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from ck3loc.core import settings
    from ck3loc.desktop.theme import stylesheet
    from ck3loc.desktop.main_window import MainWindow
    from ck3loc.desktop.workers import ModRow
    from ck3loc.desktop.export_dialog import ExportScopeDialog
    from ck3loc.core.ops import WHAT_ALL, WHAT_MISSING, WHAT_OUTDATED, WHAT_STALE

    output = ROOT / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        os.environ["CK3LOC_DATA"] = str(base / "data")
        os.environ["CK3LOC_PDX_MOD_DIR"] = str(base / "mods")
        settings.save({"scan_on_start": False, "fetch_covers": False,
                       "steam_path": str(base / "steam"), "ui_lang": "ru"})
        app = QApplication([])
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf"):
            if (fonts / name).exists():
                QFontDatabase.addApplicationFont(str(fonts / name))
        app.setFont(QFont("Segoe UI", 10))
        renderer = QSvgRenderer(str(output / "community-cover.svg"))
        cover = QImage(1024, 1024, QImage.Format.Format_ARGB32)
        painter = QPainter(cover)
        renderer.render(painter)
        painter.end()
        cover.save(str(ROOT / "workshop/ck3loc_community_database/thumbnail.png"))
        app.setStyleSheet(stylesheet("dark"))
        win = MainWindow()
        win.resize(1440, 960)
        win.status_label.setText("Демонстрационные данные • CK3 Localization Manager")
        win.library.set_rows([
            ModRow("900000001", "Royal Court Stories · Demo", 2, 68.0, "96 пропущено", True, "10.09.2026", 0, True),
            ModRow("900000002", "Dynasty Traditions · Demo", 2, 100.0, "полный", True, "09.09.2026", 0, True),
            ModRow("900000003", "Medieval Chronicles · Demo", 2, 42.0, "174 пропущено", True, "08.09.2026", 0, False),
            ModRow("900000004", "Pilgrimage Events · Demo", 1, 0.0, "нет перевода", True, "07.09.2026", 0, False),
            ModRow("900000005", "Heraldry Collection · Demo", 0, None, "нет локализации", False, "06.09.2026", 0, False),
        ])
        win.show()

        def capture(widget, name):
            for _ in range(8):
                app.processEvents()
            if not widget.grab().save(str(output / name)):
                raise RuntimeError(name)

        capture(win, "01-library.png")
        mod = base / "900000001"
        (mod / "localization").mkdir(parents=True)
        (mod / "descriptor.mod").write_text('name="Royal Court Stories · Demo"\nversion="1.0"\n', encoding="utf-8")
        strings = [
            ("court_welcome", "Welcome to the royal court.", "Добро пожаловать ко двору."),
            ("court_council", "The council awaits your decision.", "Совет ждёт вашего решения."),
            ("court_dynasty", "The legacy of our dynasty", "Наследие нашей династии"),
            ("court_feast", "A feast in the great hall", "Пир в большом зале"),
            ("court_visitor", "A visitor from distant lands", ""),
            ("court_oath", "An oath of loyalty", ""),
            ("court_secret", "Whispers in the corridor", ""),
            ("court_journey", "The journey begins", ""),
        ]
        for lang, index in [("english", 1), ("russian", 2)]:
            text = 'l_' + lang + ':\n' + ''.join(f' {row[0]}:0 "{row[index]}"\n' for row in strings if row[index])
            (mod / "localization" / f"court_l_{lang}.yml").write_text(text, encoding="utf-8-sig")
        win.mod_page.load(mod.name, mod_dir=mod)
        win.mod_page.info.setText(win.mod_page.info.text().replace(str(mod), "Steam/steamapps/workshop/content/1158310/900000001"))
        win.stack.setCurrentWidget(win.mod_page)
        win.page_title.hide()
        capture(win, "02-mod.png")
        win.mod_page.tabs.setCurrentIndex(1)
        win.mod_page.rows_table.selectRow(0)
        capture(win, "03-editor.png")
        from ck3loc.core.glossary_seed import seed_glossary
        seed_glossary(win.glossary.conn)
        win.go("glossary")
        capture(win, "04-glossary.png")
        dialog = ExportScopeDialog({WHAT_ALL: 300, WHAT_MISSING: 96, WHAT_OUTDATED: 108, WHAT_STALE: 12})
        dialog.show()
        capture(dialog, "05-export.png")
        dialog.close()
        win.close()
        app.processEvents()
    print("Gallery saved to docs/images")


if __name__ == "__main__":
    main()
