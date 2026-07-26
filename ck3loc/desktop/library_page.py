"""Экран «Библиотека»: сводка-плитки, фильтры, таблица модов."""

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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ck3loc.desktop.theme import palette
from ck3loc.desktop.widgets import (
    EmptyState,
    Tile,
    align_headers,
    setup_table,
)
from ck3loc.desktop.workers import ModRow

ALL = "Все моды"
NO_TRANSLATION = "Без перевода"
PARTIAL = "Перевод неполный"
FULL = "Перевод полный"
MINE = "Мои проекты"
ERRORS = "С ошибками"
NO_LOC = "Без локализации"
FILTERS = [ALL, NO_TRANSLATION, PARTIAL, FULL, MINE, ERRORS, NO_LOC]


class LibraryPage(QWidget):
    open_mod = Signal(str)
    rescan = Signal()
    batch = Signal()

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.rows: list[ModRow] = []
        self._shown: list[ModRow] = []
        self._scanned = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # --- плитки сводки ---
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tile_total = Tile("Всего модов", "text", theme,
                               "Показать все моды библиотеки")
        self.tile_none = Tile("Без перевода", "err", theme,
                              "Моды, где целевого языка нет совсем")
        self.tile_partial = Tile("Неполный", "warn", theme,
                                 "Перевод есть, но отстаёт от источника")
        self.tile_full = Tile("Готово", "ok", theme,
                              "Перевод полный")
        self.tile_errors = Tile("Ошибки", "warn", theme,
                                "Моды с проблемами в файлах локализации")
        self.tiles = {
            ALL: self.tile_total,
            NO_TRANSLATION: self.tile_none,
            PARTIAL: self.tile_partial,
            FULL: self.tile_full,
            ERRORS: self.tile_errors,
        }
        for name, tile in self.tiles.items():
            tiles.addWidget(tile)
            tile.clicked.connect(lambda n=name: self._set_filter(n))
        root.addLayout(tiles)

        # --- панель управления ---
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.btn_scan = QPushButton("Сканировать библиотеку")
        self.btn_scan.setProperty("accent", "true")
        self.btn_scan.setToolTip("Обновить список модов и снять снимки (F5)")
        self.btn_scan.clicked.connect(self.rescan.emit)
        controls.addWidget(self.btn_scan)
        self.btn_batch = QPushButton("Перевести всё без перевода…")
        self.btn_batch.clicked.connect(self.batch.emit)
        controls.addWidget(self.btn_batch)
        controls.addSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию или ID мода…   (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_table)
        controls.addWidget(self.search, stretch=1)
        self.filter = QComboBox()
        self.filter.addItems(FILTERS)
        self.filter.setMinimumWidth(180)
        self.filter.currentIndexChanged.connect(self.refresh_table)
        controls.addWidget(self.filter)
        root.addLayout(controls)

        # --- таблица и пустое состояние ---
        self.area = QStackedWidget()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Мод", "ID", "Языки", "Перевод", "Состояние", "Обновлён"]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 105)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 190)
        self.table.setColumnWidth(5, 100)
        setup_table(self.table)
        self.table.doubleClicked.connect(self._open_current)
        align_headers(self.table, left_columns=(0, 4), right_columns=(1, 2, 3, 5))
        self.area.addWidget(self.table)

        self.empty = EmptyState(
            "Библиотека ещё не просканирована",
            "Нажмите «Сканировать библиотеку» — приложение найдёт все моды "
            "Crusader Kings 3 из мастерской Steam и покажет, что переведено, "
            "а что нет.",
            "Сканировать библиотеку",
        )
        self.empty.button.clicked.connect(self.rescan.emit)
        self.area.addWidget(self.empty)
        root.addWidget(self.area, stretch=1)

        self.footer = QLabel("Двойной клик по строке — открыть карточку мода")
        self.footer.setProperty("role", "dim")
        root.addWidget(self.footer)

        self.set_rows([])
        self.area.setCurrentWidget(self.empty)

    # ---------- данные ----------

    def apply_theme(self, theme: str):
        self.theme = theme
        for tile in self.tiles.values():
            tile.apply_theme(theme)
        self.refresh_table()

    def set_rows(self, rows: list[ModRow]):
        self.rows = rows
        self._scanned = True
        with_loc = [r for r in rows if r.has_loc]
        no_loc = len(rows) - len(with_loc)
        self.tile_total.set_value(
            len(rows), f"{no_loc} без локализации" if no_loc else ""
        )
        self.tile_none.set_value(sum(1 for r in with_loc if r.coverage == 0.0))
        self.tile_partial.set_value(
            sum(1 for r in with_loc
                if r.coverage is not None and 0 < r.coverage < 100)
        )
        self.tile_full.set_value(sum(1 for r in with_loc if r.coverage == 100.0))
        errors = sum(1 for r in rows if r.errors)
        self.tile_errors.set_value(errors)
        self.refresh_table()

    def _set_filter(self, name: str):
        idx = self.filter.findText(name)
        if idx >= 0:
            self.filter.setCurrentIndex(idx)

    def _passes(self, r: ModRow, mode: str) -> bool:
        if mode == NO_TRANSLATION:
            return r.has_loc and r.coverage == 0.0
        if mode == PARTIAL:
            return r.coverage is not None and 0 < r.coverage < 100
        if mode == FULL:
            return r.coverage == 100.0
        if mode == MINE:
            return r.tracked
        if mode == ERRORS:
            return r.errors > 0
        if mode == NO_LOC:
            return not r.has_loc
        return True

    def refresh_table(self):
        query = self.search.text().strip().lower()
        mode = self.filter.currentText()
        c = palette(self.theme)
        for name, tile in self.tiles.items():
            tile.set_active(name == mode)

        shown = [
            r for r in self.rows
            if self._passes(r, mode)
            and (not query or query in r.name.lower() or query in r.mod_id)
        ]
        self._shown = shown
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            name_item = QTableWidgetItem(
                ("★  " if r.tracked else "") + r.name
            )
            name_item.setToolTip(
                f"{r.name}\nID {r.mod_id}"
                + ("\nЗаведён проект перевода" if r.tracked else "")
            )
            self.table.setItem(i, 0, name_item)

            id_item = QTableWidgetItem(r.mod_id)
            id_item.setForeground(QColor(c["text_dim"]))
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(i, 1, id_item)

            langs = QTableWidgetItem(str(r.n_langs) if r.has_loc else "—")
            langs.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if not r.has_loc:
                langs.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 2, langs)

            cov = QTableWidgetItem(
                "—" if r.coverage is None else f"{r.coverage:.0f}%"
            )
            cov.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if r.coverage is not None:
                cov.setForeground(QColor(
                    c["ok"] if r.coverage == 100 else
                    c["err"] if r.coverage == 0 else c["warn"]
                ))
            else:
                cov.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 3, cov)

            state = QTableWidgetItem(
                f"{r.state} · {r.errors} ошиб." if r.errors else r.state
            )
            if r.errors:
                state.setForeground(QColor(c["warn"]))
            elif not r.has_loc:
                state.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 4, state)

            upd = QTableWidgetItem(r.updated or "—")
            upd.setForeground(QColor(c["text_dim"]))
            upd.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(i, 5, upd)

        self._update_area(shown, mode, query)

    def _update_area(self, shown: list, mode: str, query: str):
        if not self._scanned or not self.rows:
            self.empty.set_text(
                "Библиотека ещё не просканирована",
                "Нажмите «Сканировать библиотеку» — приложение найдёт все моды "
                "Crusader Kings 3 из мастерской Steam и покажет, что переведено, "
                "а что нет.",
            )
            self.empty.button.setVisible(True)
            self.area.setCurrentWidget(self.empty)
            self.footer.setText("")
            return
        if not shown:
            self.empty.set_text(
                "Ничего не найдено",
                f"По фильтру «{mode}»"
                + (f" и запросу «{query}»" if query else "")
                + " модов нет. Измените фильтр или очистите поиск.",
            )
            self.empty.button.setVisible(False)
            self.area.setCurrentWidget(self.empty)
            self.footer.setText("")
            return
        self.area.setCurrentWidget(self.table)
        self.footer.setText(
            f"Показано {len(shown)} из {len(self.rows)} · "
            f"двойной клик по строке — открыть карточку мода"
        )

    def _open_current(self):
        i = self.table.currentRow()
        if 0 <= i < len(self._shown):
            self.open_mod.emit(self._shown[i].mod_id)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def set_busy(self, busy: bool):
        self.btn_scan.setEnabled(not busy)
        self.btn_batch.setEnabled(not busy)
        self.btn_scan.setText(
            "Сканирование…" if busy else "Сканировать библиотеку"
        )
        if busy and self.area.currentWidget() is self.empty:
            self.empty.set_text("Идёт сканирование…",
                                "Читаю моды и снимаю снимки локализаций.")
            self.empty.button.setVisible(False)
