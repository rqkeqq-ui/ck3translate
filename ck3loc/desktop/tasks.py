"""Фоновые операции окон и подтверждение с прокручиваемым списком.

Долгие действия (сканирование модов, выгрузка, импорт, подготовка записи)
выполняются в отдельном потоке со своим соединением SQLite, чтобы окно
не зависало. Результаты передаются обратно обычными объектами; объекты с
соединением потока (ProjectContext) наружу не отдаются.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ck3loc.core.i18n import tr
from ck3loc.core.jobs import CancellationToken


class Task(QThread):
    """Выполнить fn(conn, report, token) в фоне; report(i, total, text)."""

    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.token = CancellationToken()

    def cancel(self) -> None:
        self.token.cancel()

    def run(self):
        from ck3loc.core import db

        conn = db.connect()
        try:
            result = self.fn(conn, self.progress.emit, self.token)
        except Exception as exc:  # noqa: BLE001 — показываем в окне, а не роняем поток
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)
        finally:
            conn.close()


class ConfirmDialog(QDialog):
    """Сводка + подробный список в прокручиваемом поле; окно можно растягивать."""

    def __init__(self, title: str, summary: str, details: str = '', *, ok_text='Продолжить',
                 cancel_text='Отмена', parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr(title))
        self.setSizeGripEnabled(True)
        self.resize(760, 460 if details else 220)
        v = QVBoxLayout(self)
        label = QLabel(summary)
        label.setWordWrap(True)
        v.addWidget(label)
        if details:
            box = QPlainTextEdit(details)
            box.setReadOnly(True)
            box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            v.addWidget(box, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(tr(ok_text))
        ok.setProperty('accent', 'true')
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        if cancel_text:
            cancel = QPushButton(tr(cancel_text))
            cancel.clicked.connect(self.reject)
            row.addWidget(cancel)
        v.addLayout(row)

    @classmethod
    def ask(cls, parent, title, summary, details='', **kwargs) -> bool:
        return cls(title, summary, details, parent=parent, **kwargs).exec() == QDialog.DialogCode.Accepted

    @classmethod
    def inform(cls, parent, title, summary, details='') -> None:
        cls(title, summary, details, ok_text='Закрыть', cancel_text='', parent=parent).exec()


def run_with_progress(parent, text: str, fn):
    """Выполнить fn(conn, report, token) в фоне, показывая окно ожидания; вернуть (результат, ошибка)."""
    from PySide6.QtCore import QEventLoop, Qt
    from PySide6.QtWidgets import QProgressDialog

    dialog = QProgressDialog(text, None, 0, 0, parent)
    dialog.setWindowTitle(tr('Подождите'))
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(300)
    dialog.setCancelButton(None)
    outcome = {'result': None, 'error': ''}
    loop = QEventLoop()
    task = Task(fn, parent)
    task.succeeded.connect(lambda result: outcome.__setitem__('result', result))
    task.failed.connect(lambda error: outcome.__setitem__('error', error))
    task.finished.connect(loop.quit)
    task.start()
    loop.exec()
    dialog.close()
    return outcome['result'], outcome['error']


class SplitControl(QWidget):
    """«Разделить на части»: на N архивов поровну или по N строк в архиве.

    Выбранный режим и оба значения запоминаются между запусками.
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from ck3loc.core import settings
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.split = QCheckBox(tr('Разделить на части'))
        self.split.setToolTip(tr('Большое задание делится на несколько ZIP-архивов; '
                                 'файл с промптом один на все архивы.'))
        row.addWidget(self.split)
        self.mode = QComboBox()
        self.mode.addItem(tr('на число архивов'), 'archives')
        self.mode.addItem(tr('по числу строк в архиве'), 'rows')
        row.addWidget(self.mode)
        self.size = QSpinBox()
        self.size.setMaximumWidth(150)
        row.addWidget(self.size)
        row.addStretch(1)
        self._values = {'archives': int(settings.get('export_archives') or 5),
                        'rows': int(settings.get('export_rows_per_archive') or 250)}
        self.mode.setCurrentIndex(max(0, self.mode.findData(settings.get('export_split_mode') or 'archives')))
        self._apply_mode()
        self.split.toggled.connect(self._toggled)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.size.valueChanged.connect(self._value_changed)
        self._toggled(False)

    def _apply_mode(self):
        mode = self.mode.currentData()
        self.size.blockSignals(True)
        if mode == 'rows':
            self.size.setRange(1, 1_000_000)
            self.size.setSingleStep(50)
            self.size.setSuffix(' ' + tr('строк'))
        else:
            self.size.setRange(2, 100)
            self.size.setSingleStep(1)
            self.size.setSuffix(' ' + tr('архивов'))
        self.size.setValue(self._values[mode])
        self.size.blockSignals(False)

    def _toggled(self, on):
        self.mode.setEnabled(on)
        self.size.setEnabled(on)
        self.changed.emit()

    def _mode_changed(self, *_):
        from ck3loc.core import settings
        settings.set_value('export_split_mode', self.mode.currentData())
        self._apply_mode()
        self.changed.emit()

    def _value_changed(self, value):
        from ck3loc.core import settings
        mode = self.mode.currentData()
        self._values[mode] = value
        settings.set_value('export_archives' if mode == 'archives' else 'export_rows_per_archive', value)
        self.changed.emit()

    def kwargs(self) -> dict:
        """Параметры для package_sizes / write_package."""
        if not self.split.isChecked():
            return {'archives': 1}
        if self.mode.currentData() == 'rows':
            return {'rows_per_archive': self.size.value()}
        return {'archives': self.size.value()}
