"""Диалог выгрузки задания: выбор объёма и формата."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ck3loc.core.ops import WHAT_ALL, WHAT_MISSING, WHAT_OUTDATED, WHAT_STALE
from ck3loc.desktop.widgets import Card


class ExportScopeDialog(QDialog):
    """Что именно выгружать: только недостающее или всё подряд."""

    def __init__(self, counts: dict[str, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выгрузка задания для перевода")
        self.resize(560, 380)
        v = QVBoxLayout(self)
        v.setSpacing(12)

        card = Card("Что выгрузить")
        self.options: list[tuple[QRadioButton, str]] = []

        def add_option(text: str, what: str, hint: str, enabled: bool = True):
            radio = QRadioButton(f"{text} — {counts.get(what, 0)} строк")
            radio.setEnabled(enabled and counts.get(what, 0) > 0)
            card.add(radio)
            lab = QLabel(hint)
            lab.setProperty("role", "dim")
            lab.setWordWrap(True)
            lab.setContentsMargins(24, 0, 0, 6)
            card.add(lab)
            self.options.append((radio, what))

        add_option(
            "Только недостающие", WHAT_MISSING,
            "Строки, которых нет ни в переводе мода, ни в вашей базе. "
            "Обычный выбор: не тратит деньги и не трогает готовый перевод.",
        )
        add_option(
            "Недостающие и устаревшие", WHAT_OUTDATED,
            "Плюс строки, у которых автор мода изменил исходный текст "
            "после того, как вы их перевели.",
        )
        add_option(
            "Только устаревшие", WHAT_STALE,
            "Ничего нового, только освежить те, что разошлись с источником.",
        )
        add_option(
            "Всё, включая перевод автора мода", WHAT_ALL,
            "Полная переработка локализации. Осторожно: заменит собой "
            "существующий перевод мода.",
        )
        v.addWidget(card)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Формат файла:"))
        self.fmt = QComboBox()
        self.fmt.addItem("JSONL — для нейросети в чате", "jsonl")
        self.fmt.addItem("XLIFF 2.1 — для переводческих программ", "xliff")
        fmt_row.addWidget(self.fmt, stretch=1)
        v.addLayout(fmt_row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton("Выгрузить…")
        self.btn_ok.setProperty("accent", "true")
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        v.addLayout(btns)

        # по умолчанию — первый доступный вариант, начиная с «недостающих»
        for radio, _what in self.options:
            if radio.isEnabled():
                radio.setChecked(True)
                break
        else:
            self.btn_ok.setEnabled(False)

    def scope(self) -> str:
        for radio, what in self.options:
            if radio.isChecked():
                return what
        return WHAT_MISSING

    def format(self) -> str:
        return self.fmt.currentData()
