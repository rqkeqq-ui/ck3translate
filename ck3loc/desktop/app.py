"""Точка входа GUI."""

from __future__ import annotations

import sys
import traceback


def _excepthook(exc_type, exc, tb):
    """Показывать пользователю понятное окно вместо тихого падения."""
    from PySide6.QtWidgets import QMessageBox

    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        from ck3loc.core.db import data_dir

        log = data_dir() / "error.log"
        with log.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        hint = f"\n\nПодробности записаны в {log}"
    except Exception:  # noqa: BLE001
        hint = ""
    QMessageBox.critical(
        None, "Ошибка",
        f"Произошла ошибка:\n\n{exc}{hint}\n\n"
        f"Приложение продолжит работу, но действие могло не выполниться.",
    )


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ck3loc.core import settings
    from ck3loc.desktop.main_window import MainWindow
    from ck3loc.desktop.theme import stylesheet

    from ck3loc.core.i18n import DEFAULT_UI_LANG, set_language

    app = QApplication(sys.argv)
    app.setApplicationName("CK3 Localization Manager")
    app.setOrganizationName("ck3loc")
    app.setStyleSheet(stylesheet(settings.get("theme") or "dark"))
    sys.excepthook = _excepthook

    set_language(settings.get("ui_lang") or DEFAULT_UI_LANG)
    smoke_test = "--smoke-test" in sys.argv
    if not settings.get("ui_lang") and not smoke_test:
        _first_run(app)

    win = MainWindow()
    win.show()
    if smoke_test:
        QTimer.singleShot(1000, win.close)
    else:
        from ck3loc.desktop.community_prompt import show_community_prompt

        QTimer.singleShot(0, lambda: show_community_prompt(win))
    return app.exec()


def _first_run(app) -> None:
    """Первый запуск: спросить язык программы и язык перевода."""
    from ck3loc.core import settings
    from ck3loc.core.i18n import set_language
    from ck3loc.core.vanilla import game_languages
    from ck3loc.desktop.first_run import FirstRunDialog

    dlg = FirstRunDialog(game_languages())
    dlg.exec()
    ui_lang = dlg.ui_language()
    set_language(ui_lang)
    settings.save({
        "ui_lang": ui_lang,
        "target_lang": dlg.target_language(),
        "source_lang": dlg.source_language_default(),
    })
