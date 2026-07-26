"""Точка входа GUI."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from ck3loc.desktop.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("CK3 Localization Manager")
    win = MainWindow()
    win.show()
    return app.exec()
