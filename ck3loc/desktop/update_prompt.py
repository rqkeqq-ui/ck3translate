"""Nonblocking update check with a serialized, optional release prompt."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout

from ck3loc import __version__
from ck3loc.core import settings
from ck3loc.core.i18n import tr, tr_format
from ck3loc.core.updates import Release, check_release, should_notify


class UpdateWorker(QThread):
    result = Signal(object, str)

    def run(self):
        try:
            self.result.emit(check_release(__version__), "")
        except Exception:
            self.result.emit(None, tr("Не удалось проверить обновления. Проверьте подключение и повторите позже."))


class UpdateDialog(QDialog):
    def __init__(self, release: Release, parent=None):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle(tr("Доступна новая версия"))
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        label = QLabel(tr_format("Текущая версия: {current}. Новая версия: {latest}.", current=__version__, latest=release.version))
        label.setWordWrap(True)
        layout.addWidget(label)
        notes = QTextBrowser()
        notes.setPlainText(release.notes)
        layout.addWidget(notes)
        hint = QLabel(tr("Обновить: открыть релиз на GitHub для скачивания. Ваши переводы сохранятся."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        self.update_button = QPushButton(tr("Обновить"))
        self.update_button.clicked.connect(self.open_release)
        buttons.addWidget(self.update_button)
        self.later_button = QPushButton(tr("В следующий раз"))
        self.later_button.clicked.connect(self.reject)
        buttons.addWidget(self.later_button)
        self.skip_button = QPushButton(tr("Пропустить текущую версию"))
        self.skip_button.clicked.connect(self.skip)
        buttons.addWidget(self.skip_button)
        layout.addLayout(buttons)

    def open_release(self):
        webbrowser.open(self.release.url)
        self.accept()

    def skip(self):
        settings.set_value("skipped_update_version", self.release.version)
        self.accept()


class UpdateController(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.worker = None
        self.manual = False
        self.pending = None
        self.dialog_open = False

    def check(self, manual=False):
        if self.dialog_open or self.pending is not None:
            return
        if self.worker is not None and self.worker.isRunning():
            self.manual = self.manual or manual
            return
        self.manual = manual
        self.worker = UpdateWorker(self)
        self.worker.result.connect(self.receive)
        self.worker.start()

    def receive(self, release, error):
        self.pending = (release, error, self.manual)
        self.present()

    def present(self):
        if self.pending is None or not self.parent().isVisible():
            return
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(250, self.present)
            return
        release, error, manual = self.pending
        self.pending = None
        self.dialog_open = True
        try:
            if error:
                if manual:
                    QMessageBox.information(self.parent(), tr("Проверка обновлений"), error)
            elif should_notify(release, settings.get("skipped_update_version") or "", manual):
                UpdateDialog(release, self.parent()).exec()
            elif manual:
                QMessageBox.information(self.parent(), tr("Проверка обновлений"), tr("Установлена последняя версия."))
        finally:
            self.dialog_open = False

    def shutdown(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()
