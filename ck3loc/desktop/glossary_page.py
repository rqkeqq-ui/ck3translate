"""Экран «Глоссарий»: обязательные соответствия терминов."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import db
from ck3loc.core.glossary_seed import seed_glossary
from ck3loc.desktop.widgets import align_headers

MODES = {
    "required": "обязательный",
    "preferred": "предпочтительный",
    "forbidden": "не переводить",
}


class GlossaryPage(QWidget):
    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.conn = db.connect()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        hint = QLabel(
            "Термины передаются переводчику как обязательные соответствия. "
            "Глобальный уровень действует для всех модов."
        )
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        v.addWidget(hint)

        add = QHBoxLayout()
        self.src = QLineEdit()
        self.src.setPlaceholderText("Термин (например Realm)")
        add.addWidget(self.src, stretch=1)
        self.dst = QLineEdit()
        self.dst.setPlaceholderText("Перевод (например Держава)")
        add.addWidget(self.dst, stretch=1)
        self.mode = QComboBox()
        for key, label in MODES.items():
            self.mode.addItem(label, key)
        add.addWidget(self.mode)
        btn_add = QPushButton("Добавить")
        btn_add.setProperty("accent", "true")
        btn_add.clicked.connect(self._add_clicked)
        add.addWidget(btn_add)
        v.addLayout(add)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по глоссарию…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        tools.addWidget(self.search, stretch=1)
        btn_seed = QPushButton("Загрузить стартовый словарь CK3")
        btn_seed.clicked.connect(self._seed_clicked)
        tools.addWidget(btn_seed)
        btn_del = QPushButton("Удалить выбранное")
        btn_del.clicked.connect(self.delete_selected)
        tools.addWidget(btn_del)
        v.addLayout(tools)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Термин", "Перевод", "Режим", "Уровень"]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_edit)
        align_headers(self.table, left_columns=(0, 1, 2, 3))
        v.addWidget(self.table, stretch=1)

        self.count = QLabel()
        self.count.setProperty("role", "dim")
        v.addWidget(self.count)
        self.refresh()

    def refresh(self):
        query = self.search.text().strip().lower()
        rows = self.conn.execute(
            "SELECT * FROM glossary_terms ORDER BY level, source_term"
        ).fetchall()
        rows = [
            r for r in rows
            if not query or query in r["source_term"].lower()
            or query in (r["target_term"] or "").lower()
        ]
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        self._ids = []
        for i, r in enumerate(rows):
            self._ids.append(r["id"])
            self.table.setItem(i, 0, QTableWidgetItem(r["source_term"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["target_term"] or ""))
            mode_item = QTableWidgetItem(MODES.get(r["mode"], r["mode"]))
            mode_item.setFlags(mode_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 2, mode_item)
            level = "глобальный" if r["level"] == "global" else r["level"]
            if r["level"] == "mod" and r["mod_id"]:
                level = f"мод {r['mod_id']}"
            lvl_item = QTableWidgetItem(level)
            lvl_item.setFlags(lvl_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 3, lvl_item)
        self.table.blockSignals(False)
        total = self.conn.execute(
            "SELECT COUNT(*) AS n FROM glossary_terms"
        ).fetchone()["n"]
        self.count.setText(f"Терминов в глоссарии: {total}")

    def _on_edit(self, item):
        row = item.row()
        if row >= len(self._ids):
            return
        term_id = self._ids[row]
        field = "source_term" if item.column() == 0 else "target_term"
        if item.column() > 1:
            return
        self.conn.execute(
            f"UPDATE glossary_terms SET {field}=? WHERE id=?",
            (item.text(), term_id),
        )
        self.conn.commit()

    def add_term(self) -> bool:
        """Добавить термин. Возвращает False, если поле пустое."""
        src = self.src.text().strip()
        dst = self.dst.text().strip()
        if not src:
            return False
        self.conn.execute(
            """INSERT INTO glossary_terms (level, source_term, target_term, mode)
               VALUES ('global', ?, ?, ?)""",
            (src, dst, self.mode.currentData()),
        )
        self.conn.commit()
        self.src.clear()
        self.dst.clear()
        self.refresh()
        return True

    def _add_clicked(self):
        if not self.add_term():
            QMessageBox.information(self, "Глоссарий", "Введите термин.")

    def delete_selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return
        for r in rows:
            if r < len(self._ids):
                self.conn.execute(
                    "DELETE FROM glossary_terms WHERE id=?", (self._ids[r],)
                )
        self.conn.commit()
        self.refresh()

    def seed(self) -> int:
        """Загрузить стартовый словарь. Возвращает число добавленных терминов."""
        n = seed_glossary(self.conn)
        self.refresh()
        return n

    def _seed_clicked(self):
        n = self.seed()
        QMessageBox.information(
            self, "Глоссарий",
            f"Добавлено терминов: {n}." if n
            else "Стартовый словарь уже загружен.",
        )

    def close_db(self):
        self.conn.close()
