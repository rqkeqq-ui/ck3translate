"""Экран «Библиотека»: сводка-плитки, фильтры, таблица модов."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
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

from ck3loc.core import settings
from ck3loc.core.i18n import tr_format
from ck3loc.desktop.theme import palette
from ck3loc.desktop.widgets import (
    EmptyState,
    SortItem,
    Tile,
    align_headers,
    setup_table,
)
from ck3loc.desktop.workers import ModRow

ALL = "Все моды"
NO_TRANSLATION = "Без перевода"
PARTIAL = "Перевод неполный"
FULL = "Перевод полный"
EXTERNAL = "Переведён другим модом"
RUSSIFIERS = "Моды-русификаторы"
MINE = "Мои проекты"
ERRORS = "С ошибками"
NO_LOC = "Без локализации"
FILTERS = [ALL, NO_TRANSLATION, PARTIAL, FULL, EXTERNAL, RUSSIFIERS,
           MINE, ERRORS, NO_LOC]


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
        self._cover_cache: dict = {}

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
        self.tile_external = Tile("Чужой перевод", "info", theme,
                                  "Переведены отдельными модами-русификаторами")
        self.tile_errors = Tile("Ошибки", "warn", theme,
                                "Моды с проблемами в файлах локализации")
        self.tiles = {
            ALL: self.tile_total,
            NO_TRANSLATION: self.tile_none,
            PARTIAL: self.tile_partial,
            FULL: self.tile_full,
            EXTERNAL: self.tile_external,
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
        self.btn_mod_dir = QPushButton("Папка модов CK3")
        self.btn_mod_dir.setToolTip(
            "Открыть Documents\\Paradox Interactive\\Crusader Kings III\\mod"
        )
        self.btn_mod_dir.clicked.connect(self.open_mod_dir)
        controls.addWidget(self.btn_mod_dir)
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
        self.table.setColumnWidth(2, 92)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 190)
        self.table.setColumnWidth(5, 100)
        setup_table(self.table)
        self.table.doubleClicked.connect(self._open_current)
        align_headers(self.table, left_columns=(0, 4), right_columns=(1, 2, 3, 5))
        # сортировка по любому столбцу; числа и даты сортируются как числа
        # и даты, а не как строки (см. sort_key в refresh_table)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionsClickable(True)
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
            len(rows),
            tr_format("{n} без локализации", n=no_loc) if no_loc else "",
        )
        self.tile_none.set_value(sum(1 for r in with_loc if r.coverage == 0.0))
        self.tile_partial.set_value(
            sum(1 for r in with_loc
                if r.coverage is not None and 0 < r.coverage < 100)
        )
        self.tile_full.set_value(
            sum(1 for r in with_loc if r.coverage == 100.0)
        )
        russifiers = sum(1 for r in rows if r.translates)
        self.tile_external.set_value(
            sum(1 for r in rows if r.provider_name),
            tr_format("{n} русификаторов", n=russifiers) if russifiers else "",
        )
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
        if mode == EXTERNAL:
            return bool(r.provider_name)
        if mode == RUSSIFIERS:
            return r.translates > 0
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
        # на время заполнения сортировку отключаем, иначе строки «уезжают»
        # прямо во время вставки
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        show_covers = bool(settings.get("show_covers_in_list"))
        self.table.setIconSize(QSize(56, 32) if show_covers else QSize(0, 0))
        self.table.verticalHeader().setDefaultSectionSize(
            38 if show_covers else 30
        )
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            prefix = "★  " if r.tracked else ("⇄  " if r.translates else "")
            name_item = SortItem(prefix + r.name, r.name.lower())
            name_item.setData(Qt.ItemDataRole.UserRole, r.mod_id)
            if show_covers:
                icon = self._cover_icon(r.mod_id)
                if icon is not None:
                    name_item.setIcon(icon)
            tip = [r.name, f"ID {r.mod_id}"]
            if r.tracked:
                tip.append("Заведён проект перевода")
            if r.provider_name:
                tip.append(
                    f"Часть перевода даёт мод «{r.provider_name}»: "
                    f"покрывает {r.provider_total} строк, "
                    f"из них новых {r.provider_new}"
                )
            if r.translates:
                tip.append(f"Это мод-русификатор для {r.translates} модов")
            name_item.setToolTip("\n".join(tip))
            self.table.setItem(i, 0, name_item)

            id_item = SortItem(
                r.mod_id, int(r.mod_id) if r.mod_id.isdigit() else 0
            )
            id_item.setForeground(QColor(c["text_dim"]))
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(i, 1, id_item)

            langs = SortItem(str(r.n_langs) if r.has_loc else "—",
                             r.n_langs if r.has_loc else -1)
            langs.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if not r.has_loc:
                langs.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 2, langs)

            cov = SortItem(
                "—" if r.coverage is None else f"{r.coverage:.0f}%",
                -1.0 if r.coverage is None else r.coverage,
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

            state = SortItem(
                f"{r.state} · {r.errors} ошиб." if r.errors else r.state,
                r.state.lower(),
            )
            if r.provider_name:
                state.setForeground(QColor(c["info"]))
                state.setToolTip(
                    f"Учтён перевод из мода «{r.provider_name}» "
                    f"(+{r.provider_new} строк)"
                )
            elif r.translates:
                state.setForeground(QColor(c["info"]))
            elif r.errors:
                state.setForeground(QColor(c["warn"]))
            elif not r.has_loc:
                state.setForeground(QColor(c["text_dim"]))
            self.table.setItem(i, 4, state)

            upd = SortItem(r.updated or "—", r.updated_ts)
            upd.setForeground(QColor(c["text_dim"]))
            upd.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(i, 5, upd)

        self.table.setSortingEnabled(was_sorting)
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
        self.footer.setText(tr_format(
            "Показано {shown} из {total} · двойной клик по строке — "
            "открыть карточку мода",
            shown=len(shown), total=len(self.rows),
        ))

    def _open_current(self):
        # после сортировки порядок строк не совпадает со списком, поэтому
        # ID мода берём из самой ячейки
        item = self.table.item(self.table.currentRow(), 0)
        if item is not None:
            mod_id = item.data(Qt.ItemDataRole.UserRole)
            if mod_id:
                self.open_mod.emit(str(mod_id))

    def _cover_icon(self, mod_id: str):
        """Миниатюра обложки из кэша; в сеть за ней список не ходит."""
        from PySide6.QtGui import QIcon, QPixmap

        from ck3loc.core.covers import cached_cover

        if mod_id in self._cover_cache:
            return self._cover_cache[mod_id]
        path = cached_cover(mod_id)
        icon = None
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull():
                icon = QIcon(pix)
        self._cover_cache[mod_id] = icon
        return icon

    def open_mod_dir(self):
        """Папка локальных модов CK3 — туда приложение кладёт патч-моды."""
        import os
        import subprocess

        from ck3loc.core.writer import pdx_mod_dir

        path = pdx_mod_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))  # noqa: S606 — проводник Windows
        except Exception:  # noqa: BLE001
            subprocess.Popen(["explorer", str(path)])

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
