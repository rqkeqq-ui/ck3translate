"""Экран «Библиотека»: сводка, фильтры, таблица модов."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ck3loc.desktop.theme import palette
from ck3loc.desktop.widgets import Tile, align_headers
from ck3loc.desktop.workers import ModRow

FILTERS = [
    "Все моды",
    "Без перевода",
    "Перевод неполный",
    "Перевод полный",
    "Мои проекты",
    "С ошибками",
    "Без локализации",
]


class LibraryPage(QWidget):
    open_mod = Signal(str)
    rescan = Signal()
    batch = Signal()

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.rows: list[ModRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # плитки-сводка
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tile_total = Tile("Модов установлено", theme=theme)
        self.tile_noloc = Tile("Без локализации", theme=theme, accent="text_dim")
        self.tile_none = Tile("Без перевода", theme=theme, accent="err")
        self.tile_partial = Tile("Перевод неполный", theme=theme, accent="warn")
        self.tile_full = Tile("Перевод полный", theme=theme, accent="ok")
        self.tile_errors = Tile("Ошибки в файлах модов", theme=theme, accent="warn")
        for t in (self.tile_total, self.tile_noloc, self.tile_none,
                  self.tile_partial, self.tile_full, self.tile_errors):
            tiles.addWidget(t)
        self.tile_total.clicked.connect(lambda: self._set_filter("Все моды"))
        self.tile_noloc.clicked.connect(lambda: self._set_filter("Без локализации"))
        self.tile_none.clicked.connect(lambda: self._set_filter("Без перевода"))
        self.tile_partial.clicked.connect(
            lambda: self._set_filter("Перевод неполный"))
        self.tile_full.clicked.connect(lambda: self._set_filter("Перевод полный"))
        self.tile_errors.clicked.connect(lambda: self._set_filter("С ошибками"))
        root.addLayout(tiles)

        # панель управления
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.btn_scan = QPushButton("Сканировать библиотеку")
        self.btn_scan.setProperty("accent", "true")
        self.btn_scan.clicked.connect(self.rescan.emit)
        controls.addWidget(self.btn_scan)
        self.btn_batch = QPushButton("Перевести всё без перевода…")
        self.btn_batch.clicked.connect(self.batch.emit)
        controls.addWidget(self.btn_batch)
        controls.addSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию или ID мода…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_table)
        controls.addWidget(self.search, stretch=1)
        self.filter = QComboBox()
        self.filter.addItems(FILTERS)
        self.filter.setMinimumWidth(170)
        self.filter.currentIndexChanged.connect(self.refresh_table)
        controls.addWidget(self.filter)
        root.addLayout(controls)

        # таблица
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Мод", "ID", "Языки", "Перевод", "Состояние", "Обновлён"]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3, 4, 5):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._open_current)
        align_headers(self.table, left_columns=(0, 4, 5), right_columns=(1, 3))
        root.addWidget(self.table, stretch=1)

        hint = QLabel("Двойной клик по строке — открыть карточку мода")
        hint.setProperty("role", "dim")
        root.addWidget(hint)

        self.set_rows([])

    # ---------- данные ----------

    def apply_theme(self, theme: str):
        self.theme = theme
        for t in (self.tile_total, self.tile_noloc, self.tile_none,
                  self.tile_partial, self.tile_full, self.tile_errors):
            t.apply_theme(theme)
        self.refresh_table()

    def set_rows(self, rows: list[ModRow]):
        self.rows = rows
        with_loc = [r for r in rows if r.has_loc]
        self.tile_total.set_value(len(rows))
        self.tile_noloc.set_value(len(rows) - len(with_loc))
        self.tile_none.set_value(sum(1 for r in with_loc if r.coverage == 0.0))
        self.tile_partial.set_value(
            sum(1 for r in with_loc if r.coverage is not None
                and 0 < r.coverage < 100)
        )
        self.tile_full.set_value(sum(1 for r in with_loc if r.coverage == 100.0))
        self.tile_errors.set_value(sum(1 for r in rows if r.errors))
        self.refresh_table()

    def _set_filter(self, name: str):
        idx = self.filter.findText(name)
        if idx >= 0:
            self.filter.setCurrentIndex(idx)

    def _passes(self, r: ModRow, mode: str) -> bool:
        if mode == "Без перевода":
            return r.has_loc and r.coverage == 0.0
        if mode == "Перевод неполный":
            return r.coverage is not None and 0 < r.coverage < 100
        if mode == "Перевод полный":
            return r.coverage == 100.0
        if mode == "Мои проекты":
            return r.tracked
        if mode == "С ошибками":
            return r.errors > 0
        if mode == "Без локализации":
            return not r.has_loc
        return True

    def refresh_table(self):
        query = self.search.text().strip().lower()
        mode = self.filter.currentText()
        c = palette(self.theme)
        shown = [
            r for r in self.rows
            if self._passes(r, mode)
            and (not query or query in r.name.lower() or query in r.mod_id)
        ]
        self.table.setRowCount(len(shown))
        self._shown = shown
        for i, r in enumerate(shown):
            name_item = QTableWidgetItem(r.name)
            if r.tracked:
                name_item.setText("★ " + r.name)
                name_item.setToolTip("Для этого мода заведён проект перевода")
            self.table.setItem(i, 0, name_item)

            id_item = QTableWidgetItem(r.mod_id)
            id_item.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 1, id_item)

            langs = QTableWidgetItem(str(r.n_langs) if r.has_loc else "—")
            langs.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 2, langs)

            cov_text = "—" if r.coverage is None else f"{r.coverage:.0f}%"
            cov = QTableWidgetItem(cov_text)
            cov.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if r.coverage is not None:
                color = (c["ok"] if r.coverage == 100 else
                         c["err"] if r.coverage == 0 else c["warn"])
                cov.setForeground(QColor(color))
            self.table.setItem(i, 3, cov)

            state = QTableWidgetItem(r.state)
            if r.errors:
                state.setText(f"{r.state} · {r.errors} ошиб.")
                state.setForeground(QColor(c["warn"]))
            self.table.setItem(i, 4, state)

            upd = QTableWidgetItem(r.updated or "—")
            upd.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 5, upd)

    def _open_current(self):
        i = self.table.currentRow()
        if 0 <= i < len(self._shown):
            self.open_mod.emit(self._shown[i].mod_id)

    def set_busy(self, busy: bool):
        self.btn_scan.setEnabled(not busy)
        self.btn_batch.setEnabled(not busy)
        self.btn_scan.setText(
            "Сканирование…" if busy else "Сканировать библиотеку"
        )
