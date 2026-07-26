"""Главное окно: сводка библиотеки, таблица модов, уведомления."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import db
from ck3loc.core.scanner import scan_mod
from ck3loc.core.steam import (
    find_steam_root,
    list_workshop_mod_dirs,
    read_workshop_acf,
    workshop_content_dirs,
)
from ck3loc.core.store import (
    diff_snapshots,
    latest_snapshot,
    mark_missing_mods,
    record_mod,
    take_snapshot,
)
from ck3loc.core.vanilla import game_languages

TARGET_LANG = "russian"
SOURCE_LANG = "english"


@dataclass
class ModRow:
    mod_id: str
    name: str
    n_langs: int
    coverage: float | None  # None — нет локализации/источника
    state: str
    has_loc: bool


class ScanWorker(QThread):
    progress = Signal(int, int)
    note = Signal(str)
    finished_rows = Signal(list)

    def run(self):
        conn = db.connect()
        try:
            rows: list[ModRow] = []
            root = find_steam_root()
            if root is None:
                self.note.emit("Steam не найден. Проверьте установку Steam.")
                self.finished_rows.emit([])
                return
            content = workshop_content_dirs(root)
            mod_dirs = list_workshop_mod_dirs(content)
            langs = game_languages()
            acf = read_workshop_acf()
            total = len(mod_dirs)
            for i, mod_dir in enumerate(mod_dirs, start=1):
                self.progress.emit(i, total)
                scan = scan_mod(mod_dir, langs)
                entry = acf.get(scan.mod_id)
                t_upd = int(entry.time_updated) if entry and entry.time_updated else 0
                record_mod(conn, scan, steam_time_updated=t_upd)
                if not scan.has_localization:
                    rows.append(ModRow(scan.mod_id, scan.name, 0, None,
                                       "нет локализации", False))
                    continue
                prev = latest_snapshot(conn, scan.mod_id)
                snap = take_snapshot(conn, scan, steam_time_updated=t_upd)
                if snap.is_new and prev is not None:
                    self._report_changes(conn, scan, prev["id"], snap.snapshot_id)
                src = scan.best_source_language(SOURCE_LANG) or SOURCE_LANG
                translated, of = scan.coverage(TARGET_LANG, src)
                if of == 0:
                    rows.append(ModRow(scan.mod_id, scan.name,
                                       len(scan.languages), None,
                                       f"нет {src}", True))
                elif translated == 0:
                    rows.append(ModRow(scan.mod_id, scan.name,
                                       len(scan.languages), 0.0,
                                       "нет русского", True))
                elif translated < of:
                    rows.append(ModRow(scan.mod_id, scan.name,
                                       len(scan.languages),
                                       100.0 * translated / of,
                                       f"{of - translated} пропущено", True))
                else:
                    rows.append(ModRow(scan.mod_id, scan.name,
                                       len(scan.languages), 100.0,
                                       "полный", True))
            gone = mark_missing_mods(conn, {d.name for d in mod_dirs})
            for g in gone:
                self.note.emit(
                    f"Мод {g} больше не установлен — данные и перевод "
                    f"сохранены в базе."
                )
            self.finished_rows.emit(rows)
        finally:
            conn.close()

    def _report_changes(self, conn, scan, old_id: int, new_id: int):
        parts = []
        for lang in scan.languages:
            d = diff_snapshots(conn, old_id, new_id, lang)
            if not d.empty:
                parts.append(
                    f"[{lang}] +{len(d.added)} ~{len(d.changed)} -{len(d.removed)}"
                )
        if parts:
            self.note.emit(
                f"«{scan.name}» обновился, локализация изменилась: "
                + "; ".join(parts)
            )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CK3 Localization Manager")
        self.resize(1100, 700)
        self.rows: list[ModRow] = []

        central = QWidget()
        layout = QVBoxLayout(central)

        self.summary = QLabel("Нажмите «Сканировать», чтобы найти моды.")
        layout.addWidget(self.summary)

        controls = QHBoxLayout()
        self.btn_scan = QPushButton("Сканировать библиотеку")
        self.btn_scan.clicked.connect(self.start_scan)
        controls.addWidget(self.btn_scan)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию или ID…")
        self.search.textChanged.connect(self.refresh_table)
        controls.addWidget(self.search)
        self.filter = QComboBox()
        self.filter.addItems(
            ["Все", "Без русского", "Русский неполный", "Полный русский",
             "Без локализации"]
        )
        self.filter.currentIndexChanged.connect(self.refresh_table)
        controls.addWidget(self.filter)
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Название", "Языки", "Русский", "Состояние"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.open_mod)
        layout.addWidget(self.table, stretch=1)

        layout.addWidget(QLabel("Уведомления:"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        layout.addWidget(self.log)

        self.setCentralWidget(central)
        self.worker: ScanWorker | None = None

    # --- сканирование ---

    def start_scan(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.btn_scan.setEnabled(False)
        self.progress.show()
        self.worker = ScanWorker()
        self.worker.progress.connect(self._on_progress)
        self.worker.note.connect(self.add_note)
        self.worker.finished_rows.connect(self._on_scan_done)
        self.worker.start()

    def _on_progress(self, i: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(i)

    def _on_scan_done(self, rows: list):
        self.rows = rows
        self.btn_scan.setEnabled(True)
        self.progress.hide()
        with_loc = [r for r in rows if r.has_loc]
        no_ru = [r for r in with_loc if r.coverage == 0.0]
        partial = [r for r in with_loc if r.coverage and 0 < r.coverage < 100]
        self.summary.setText(
            f"Модов установлено: {len(rows)} · С локализацией: {len(with_loc)} · "
            f"Без русского: {len(no_ru)} · Русский неполный: {len(partial)}"
        )
        self.refresh_table()
        self.add_note("Сканирование завершено.")

    # --- таблица ---

    def refresh_table(self):
        query = self.search.text().strip().lower()
        mode = self.filter.currentText()
        shown = []
        for r in self.rows:
            if query and query not in r.name.lower() and query not in r.mod_id:
                continue
            if mode == "Без русского" and not (r.has_loc and r.coverage == 0.0):
                continue
            if mode == "Русский неполный" and not (
                r.coverage and 0 < r.coverage < 100
            ):
                continue
            if mode == "Полный русский" and r.coverage != 100.0:
                continue
            if mode == "Без локализации" and r.has_loc:
                continue
            shown.append(r)
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            cov = "" if r.coverage is None else f"{r.coverage:.1f}%"
            for col, text in enumerate(
                [r.mod_id, r.name, str(r.n_langs) if r.has_loc else "—",
                 cov, r.state]
            ):
                item = QTableWidgetItem(text)
                if col in (0, 2, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(i, col, item)

    def open_mod(self):
        row_i = self.table.currentRow()
        if row_i < 0:
            return
        mod_id = self.table.item(row_i, 0).text()
        from ck3loc.desktop.mod_dialog import ModDialog

        try:
            dlg = ModDialog(mod_id, parent=self)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Ошибка", str(e))
            return
        dlg.note.connect(self.add_note)
        dlg.exec()

    def add_note(self, text: str):
        self.log.appendPlainText(text)
