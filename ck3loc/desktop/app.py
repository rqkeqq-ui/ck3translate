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
        _smoke_imports()
        QTimer.singleShot(1000, win.close)
    else:
        from ck3loc.desktop.community_prompt import show_community_prompt
        from ck3loc.desktop.update_prompt import UpdateController

        win.updates = UpdateController(win)
        win.settings_page.update_requested.connect(lambda: win.updates.check(manual=True))
        app.aboutToQuit.connect(win.updates.shutdown)

        def startup():
            show_community_prompt(win)
            if win.isVisible():
                win.updates.check()

        QTimer.singleShot(0, startup)
    return app.exec()


def _smoke_imports() -> None:
    """Собранный бинарник должен содержать модули, которые грузятся лениво."""
    import filelock  # noqa: F401
    import httpx  # noqa: F401
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: F401

    import ck3loc.desktop.batch_dialog  # noqa: F401
    import ck3loc.desktop.history_dialog  # noqa: F401
    import ck3loc.desktop.review_dialog  # noqa: F401
    import ck3loc.providers.chatgpt  # noqa: F401
    from ck3loc.core import db
    from ck3loc.core.exchange import FORMATS
    from ck3loc.core.jobs import recover_interrupted

    from ck3loc.providers.web_free import WEB_FREE_PROVIDERS, _library

    assert FORMATS == {"jsonl", "xliff", "yml"}
    assert jwt.algorithms.has_crypto
    # Бесплатные веб-переводчики грузятся только при переводе — проверяем, что библиотека в сборке.
    pool = set(_library().translators_pool)
    assert all(p.engine in pool for p in WEB_FREE_PROVIDERS), pool
    conn = db.connect()
    try:
        recover_interrupted(conn)
    finally:
        conn.close()


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
