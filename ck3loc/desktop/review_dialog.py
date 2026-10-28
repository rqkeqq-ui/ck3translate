"""Selectable review shared by imports, translation drafts, removal and undo."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)
from ck3loc.core.i18n import tr, tr_format


class ReviewDialog(QDialog):
    def __init__(self, rows, title='Предпросмотр изменений', *, providers=None,
                 default_changes=('add',), allow_game_files=False,
                 action_label='Применить {n} выбранных строк', groups=None, display_keys=None,
                 parent=None):
        super().__init__(parent)
        self.rows = rows
        self.action_label = action_label
        self.setWindowTitle(tr(title))
        self.setSizeGripEnabled(True)
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            self.resize(min(1400, int(screen.width() * 0.85)), min(860, int(screen.height() * 0.85)))
        else:
            self.resize(1200, 760)
        v = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Поиск по ключу или тексту…'))
        self.search.textChanged.connect(self.filter_rows)
        v.addWidget(self.search)
        groups, display_keys = groups or {}, display_keys or {}
        self.table = QTableWidget(len(rows), 8)
        self.table.setHorizontalHeaderLabels([tr(s) for s in ['Выбрать', 'Ключ', 'Источник', 'Текущий перевод', 'Новый перевод', 'Источник перевода', 'Состояние', 'Мод']])
        from ck3loc.desktop.widgets import resizable_columns
        resizable_columns(self.table, {0: 70, 1: 220, 2: 300, 3: 260, 4: 300, 5: 140, 6: 130})
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        for i, row in enumerate(rows):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            if row.change in {'blocked', 'unchanged'}:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setCheckState(Qt.CheckState.Checked if row.change in default_changes else Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, item)
            for j, value in enumerate([display_keys.get(row.key, row.key), row.source, row.before, row.after,
                                      (providers or {}).get(row.key, ''), tr(row.reason or row.change),
                                      groups.get(row.key, '')], 1):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(i, j, item)
        # Пустая колонка источника не занимает место (она нужна только при удалении).
        self.table.setColumnHidden(5, not any((providers or {}).get(r.key) for r in rows))
        # Колонка мода нужна только в общем предпросмотре нескольких модов; ставим её второй.
        self.table.setColumnHidden(7, not groups)
        if groups:
            self.table.horizontalHeader().moveSection(7, 1)
            self.table.setColumnWidth(7, 220)
        self.table.itemChanged.connect(self.update_count)
        self.table.currentCellChanged.connect(self.show_details)
        # Полные тексты выбранной строки: длинные описания в таблице не помещаются.
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(tr('Выберите строку, чтобы увидеть исходник, текущий и новый перевод целиком.'))
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        v.addWidget(splitter, 1)
        self.count = QLabel()
        v.addWidget(self.count)
        self.update_files = QCheckBox(tr('Также убрать из записанных файлов менеджера'))
        self.update_files.setChecked(allow_game_files)
        self.update_files.setVisible(allow_game_files)
        v.addWidget(self.update_files)
        tools = QHBoxLayout()
        select = QPushButton(tr('Все результаты фильтра'))
        select.clicked.connect(self.select_visible)
        tools.addWidget(select)
        self.apply = QPushButton(tr('Применить выбранное'))
        self.apply.clicked.connect(self.accept)
        tools.addWidget(self.apply)
        cancel = QPushButton(tr('Отмена'))
        cancel.clicked.connect(self.reject)
        tools.addWidget(cancel)
        v.addLayout(tools)
        self.update_count()

    def show_details(self, row, *_):
        if not 0 <= row < len(self.rows):
            return
        r = self.rows[row]
        parts = [f'{r.key}', '', tr('Исходник') + ':', r.source, '', tr('Текущий перевод') + ':', r.before or '—',
                 '', tr('Новый перевод') + ':', r.after or '—']
        if r.reason:
            parts += ['', tr(r.reason)]
        self.details.setPlainText('\n'.join(parts))

    def selected_keys(self) -> set[str]:
        return {r.key for i, r in enumerate(self.rows)
                if self.table.item(i, 0).checkState() == Qt.CheckState.Checked}

    def update_count(self, *_):
        selected = self.selected_keys()
        hidden = sum(r.key in selected and self.table.isRowHidden(i) for i, r in enumerate(self.rows))
        self.count.setText(tr_format('Выбрано: {n}; скрыто фильтром: {hidden}', n=len(selected), hidden=hidden))
        self.apply.setEnabled(bool(selected))
        self.apply.setText(tr_format(self.action_label, n=len(selected)))

    def filter_rows(self, text):
        text = text.casefold().strip()
        for i, r in enumerate(self.rows):
            self.table.setRowHidden(i, bool(text and text not in ' '.join(
                self.table.item(i, col).text() for col in range(1, 8)).casefold()))
        self.update_count()

    def select_visible(self):
        for i in range(len(self.rows)):
            item = self.table.item(i, 0)
            if not self.table.isRowHidden(i) and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                item.setCheckState(Qt.CheckState.Checked)
