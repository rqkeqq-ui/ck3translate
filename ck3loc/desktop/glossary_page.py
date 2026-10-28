"""Lazy glossary snapshots loaded off the GUI thread, with stable term IDs."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget)
from ck3loc.core import db, settings
from ck3loc.core.i18n import tr, tr_format
from ck3loc.core.glossary_seed import seed_glossary

MODES = {'required': 'обязательный', 'preferred': 'предпочтительный', 'forbidden': 'не переводить'}


class GlossaryWorker(QThread):
    loaded = Signal(int, object)
    failed = Signal(int, str)
    status = Signal(int, str)

    def __init__(self, generation: int, source: str, target: str, *, import_database=False):
        super().__init__()
        self.generation, self.source, self.target = generation, source, target
        self.import_database = import_database

    def run(self):
        conn = db.connect()
        try:
            self.status.emit(self.generation, self._database_status(conn))
            effective = {}
            for r in conn.execute("""SELECT * FROM glossary_terms WHERE source_lang=? AND target_lang=?
                ORDER BY CASE origin WHEN 'user' THEN 2 WHEN 'builtin' THEN 0 ELSE 1 END,id""",
                (self.source, self.target)):
                if self.isInterruptionRequested():
                    return
                effective[(r['level'], r['mod_id'], r['source_term'].casefold())] = dict(r)
            self.loaded.emit(self.generation, sorted(effective.values(), key=lambda r: (r['level'], r['source_term'].casefold())))
        except Exception as exc:
            self.failed.emit(self.generation, str(exc))
        finally:
            conn.close()

    def _database_status(self, conn) -> str:
        """Discover (and on request re-read) the installed Workshop database."""
        from pathlib import Path
        from ck3loc.core.community_db import (describe_state, discover_community_database,
                                              import_community_glossary)
        cfg = settings.load()
        steam = cfg.get('steam_path', '')
        result = discover_community_database(Path(steam) if steam else None,
                                             enabled=bool(cfg.get('community_db_enabled', True)))
        imported = None
        if self.import_database and result.state == 'ready' and result.database is not None:
            imported = import_community_glossary(conn, result.database)
        return 'Community Database: ' + describe_state(result, source_lang=self.source,
                                                       target_lang=self.target, imported=imported)


class GlossaryModel(QAbstractTableModel):
    edited = Signal(int, str, str)
    headers = ['Термин', 'Перевод', 'Режим', 'Уровень']

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(self.headers[section])

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return row['id']
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return [row['source_term'], row['target_term'] or '', tr(MODES.get(row['mode'], row['mode'])),
                    tr('глобальный') if row['level'] == 'global' else row['level'] + ' ' + row['mod_id']][index.column()]

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsEditable if index.column() < 2 else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() > 1:
            return False
        field = 'source_term' if index.column() == 0 else 'target_term'
        if field == 'source_term' and not str(value).strip():
            return False
        row = self.rows[index.row()]
        self.edited.emit(row['id'], field, str(value))
        row[field] = str(value)
        row['origin'] = 'user'
        self.dataChanged.emit(index, index, [role, Qt.ItemDataRole.DisplayRole])
        return True

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class GlossaryPage(QWidget):
    def __init__(self, theme='dark', parent=None):
        super().__init__(parent)
        self.conn = db.connect()
        self.source_lang = settings.get('source_lang') or 'english'
        self.target_lang = settings.get('target_lang') or 'russian'
        self._generation = 0
        self._workers = set()
        self._snapshot_pair = None
        self._closed = False
        self._dirty = True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        hint = QLabel('Текущая языковая пара из Настроек. Пользовательские правки имеют приоритет.')
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.db_status = QLabel()
        self.db_status.setProperty('role', 'dim')
        self.db_status.setWordWrap(True)
        v.addWidget(self.db_status)
        add = QHBoxLayout()
        self.src, self.dst = QLineEdit(), QLineEdit()
        self.src.setPlaceholderText('Термин (например Realm)')
        self.dst.setPlaceholderText('Перевод (например Держава)')
        add.addWidget(self.src)
        add.addWidget(self.dst)
        self.mode = QComboBox()
        for key, label in MODES.items():
            self.mode.addItem(tr(label), key)
        add.addWidget(self.mode)
        btn = QPushButton('Добавить')
        btn.clicked.connect(self._add_clicked)
        add.addWidget(btn)
        v.addLayout(add)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Поиск по глоссарию…')
        self.search.setClearButtonEnabled(True)
        tools.addWidget(self.search, 1)
        self.seed_button = QPushButton('Обновить из установленной базы')
        self.seed_button.clicked.connect(self._seed_clicked)
        tools.addWidget(self.seed_button)
        open_button = QPushButton('Открыть в Workshop')
        open_button.clicked.connect(self._open_workshop)
        tools.addWidget(open_button)
        btn = QPushButton('Удалить выбранное')
        btn.clicked.connect(self.delete_selected)
        tools.addWidget(btn)
        v.addLayout(tools)
        self.model = GlossaryModel(self)
        self.model.edited.connect(self._on_edit)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.table, 1)
        self.count = QLabel()
        v.addWidget(self.count)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(150)
        self.debounce.timeout.connect(lambda: self.proxy.setFilterFixedString(self.search.text().strip()))
        self.search.textChanged.connect(lambda: self.debounce.start())

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def invalidate(self):
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def refresh(self, *, force=False, import_database=False):
        if self._closed:
            return
        self.source_lang = settings.get('source_lang') or 'english'
        self.target_lang = settings.get('target_lang') or 'russian'
        pair = self.source_lang, self.target_lang
        if not (force or self._dirty or pair != self._snapshot_pair or import_database):
            return
        self._dirty = False
        self._snapshot_pair = pair
        self._generation += 1
        for worker in self._workers:
            worker.requestInterruption()
        self.count.setText(tr('Загрузка терминов…'))
        worker = GlossaryWorker(self._generation, *pair, import_database=import_database)
        self._workers.add(worker)
        worker.loaded.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.status.connect(self._status)
        worker.finished.connect(lambda: self._workers.discard(worker))
        worker.start()

    def _loaded(self, generation, rows):
        if self._closed or generation != self._generation:
            return
        self.model.set_rows(rows)
        self.count.setText(tr_format('{source} → {target}: {total} терминов', source=self.source_lang,
                                     target=self.target_lang, total=len(rows)))
        self.seed_button.setEnabled(True)

    def _status(self, generation, text):
        if generation == self._generation and not self._closed:
            self.db_status.setText(text)

    def _failed(self, generation, error):
        if generation == self._generation and not self._closed:
            self.count.setText(error)
            self.seed_button.setEnabled(True)
            self._dirty = True

    def _on_edit(self, term_id, field, value):
        if field not in {'source_term', 'target_term'}:
            return
        self.conn.execute(f"UPDATE glossary_terms SET {field}=?,origin='user' WHERE id=?", (value, term_id))
        self.conn.commit()

    def add_term(self) -> bool:
        if not self.src.text().strip():
            return False
        self.conn.execute("""INSERT INTO glossary_terms (level,source_lang,target_lang,
            source_term,target_term,mode,origin) VALUES ('global',?,?,?,?,?,'user')""",
            (self.source_lang, self.target_lang, self.src.text().strip(), self.dst.text().strip(), self.mode.currentData()))
        self.conn.commit()
        self.src.clear()
        self.dst.clear()
        self.refresh(force=True)
        return True

    def _add_clicked(self):
        if not self.add_term():
            QMessageBox.information(self, tr('Глоссарий'), tr('Введите термин.'))

    def delete_selected(self):
        ids = {self.model.rows[self.proxy.mapToSource(i).row()]['id'] for i in self.table.selectionModel().selectedRows()}
        self.conn.executemany('DELETE FROM glossary_terms WHERE id=?', [(i,) for i in ids])
        self.conn.commit()
        self.refresh(force=True)

    def seed(self) -> int:
        n = seed_glossary(self.conn)
        self.refresh(force=True)
        return n

    def _seed_clicked(self):
        self.seed_button.setEnabled(False)
        self.refresh(force=True, import_database=True)

    def _open_workshop(self):
        import webbrowser
        from ck3loc.core.community_db import workshop_page_url
        webbrowser.open(workshop_page_url())

    def close_db(self):
        self._closed = True
        self.debounce.stop()
        for worker in list(self._workers):
            worker.requestInterruption()
            worker.wait()
        self.conn.close()
