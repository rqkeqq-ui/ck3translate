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
    from PySide6.QtWidgets import QApplication

    from ck3loc.core import settings
    from ck3loc.desktop.main_window import MainWindow
    from ck3loc.desktop.theme import stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName("CK3 Localization Manager")
    app.setOrganizationName("ck3loc")
    app.setStyleSheet(stylesheet(settings.get("theme") or "dark"))
    sys.excepthook = _excepthook

    win = MainWindow()
    win.show()
    return app.exec()
