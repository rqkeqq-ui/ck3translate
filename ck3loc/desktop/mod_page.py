"""Экран карточки мода: обзор, строки с редактором, изменения, диагностика."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import db, settings
from ck3loc.core.bundle import import_jsonl
from ck3loc.core.ops import apply_import_report, load_project_context, rows_to_translate
from ck3loc.core.scanner import semantic_hash
from ck3loc.core.status import REVIEWED
from ck3loc.core.store import set_project_option, upsert_unit
from ck3loc.core.tokens import validate_translation
from ck3loc.core.writer import apply_write_plan, build_write_plan, verify_outputs
from ck3loc.core.xliff import import_xliff
from ck3loc.desktop.theme import palette
from ck3loc.desktop.widgets import Card, align_headers, status_color, status_label

ROW_FILTERS = {
    "Все строки": None,
    "Не переведено": {"missing"},
    "Устарело": {"stale"},
    "Машинный перевод": {"machine"},
    "Проверено": {"reviewed", "approved"},
    "Конфликты и правки извне": {"conflict", "edited_outside"},
    "Родной перевод мода": {"native"},
    "Осиротевшие / только в цели": {"orphan", "extra"},
}


class ModPage(QWidget):
    back = Signal()
    note = Signal(str)
    request_translate = Signal(str)  # mod_id

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.conn = db.connect()
        self.ctx = None
        self.mod_id = ""
        self._mod_dir: Path | None = None
        self._shown_rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        head = QHBoxLayout()
        btn_back = QPushButton("← К библиотеке")
        btn_back.clicked.connect(self.back.emit)
        head.addWidget(btn_back)
        self.title = QLabel()
        self.title.setProperty("role", "h1")
        head.addWidget(self.title, stretch=1)
        root.addLayout(head)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "Обзор")
        self.tabs.addTab(self._build_rows(), "Строки")
        self.tabs.addTab(self._build_changes(), "Изменения")
        self.tabs.addTab(self._build_diag(), "Диагностика")
        root.addWidget(self.tabs, stretch=1)

    # ---------- вкладка «Обзор» ----------

    def _build_overview(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)

        self.info_card = Card("Сведения о моде")
        self.info = QLabel()
        self.info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.info.setWordWrap(True)
        self.info_card.add(self.info)
        v.addWidget(self.info_card)

        actions = Card("Действия")
        row1 = QHBoxLayout()
        self.btn_api = QPushButton("Перевести через API…")
        self.btn_api.setProperty("accent", "true")
        self.btn_api.clicked.connect(
            lambda: self.request_translate.emit(self.mod_id)
        )
        row1.addWidget(self.btn_api)
        b_exp = QPushButton("Выгрузить задание для нейросети…")
        b_exp.clicked.connect(self.do_export)
        row1.addWidget(b_exp)
        b_imp = QPushButton("Загрузить перевод из файла…")
        b_imp.clicked.connect(self.do_import)
        row1.addWidget(b_imp)
        row1.addStretch(1)
        actions.add_layout(row1)

        row2 = QHBoxLayout()
        self.btn_write = QPushButton("Записать перевод в игру")
        self.btn_write.setProperty("accent", "true")
        self.btn_write.clicked.connect(self.do_write)
        row2.addWidget(self.btn_write)
        b_ver = QPushButton("Проверить и восстановить")
        b_ver.clicked.connect(self.do_verify)
        row2.addWidget(b_ver)
        row2.addSpacing(16)
        row2.addWidget(QLabel("Куда писать:"))
        self.write_mode = QComboBox()
        self.write_mode.addItem("Внутрь мода", "in_mod")
        self.write_mode.addItem("Отдельный патч-мод", "patch_mod")
        self.write_mode.currentIndexChanged.connect(self._change_write_mode)
        row2.addWidget(self.write_mode)
        row2.addStretch(1)
        actions.add_layout(row2)
        v.addWidget(actions)

        log_card = Card("Журнал действий")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        log_card.add(self.log, stretch=1)
        v.addWidget(log_card, stretch=1)
        return w

    # ---------- вкладка «Строки» ----------

    def _build_rows(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        top = QHBoxLayout()
        self.row_filter = QComboBox()
        self.row_filter.addItems(list(ROW_FILTERS))
        self.row_filter.setMinimumWidth(220)
        self.row_filter.currentIndexChanged.connect(self.refresh_rows)
        top.addWidget(self.row_filter)
        self.row_search = QLineEdit()
        self.row_search.setPlaceholderText("Поиск по ключу или тексту…")
        self.row_search.setClearButtonEnabled(True)
        self.row_search.textChanged.connect(self.refresh_rows)
        top.addWidget(self.row_search, stretch=1)
        self.rows_count = QLabel()
        self.rows_count.setProperty("role", "dim")
        top.addWidget(self.rows_count)
        v.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.rows_table = QTableWidget(0, 4)
        self.rows_table.setHorizontalHeaderLabels(
            ["Статус", "Ключ", "Источник", "Перевод"]
        )
        h = self.rows_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.rows_table.setColumnWidth(1, 230)
        self.rows_table.verticalHeader().setVisible(False)
        self.rows_table.setShowGrid(False)
        self.rows_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rows_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.rows_table.itemSelectionChanged.connect(self._load_editor)
        align_headers(self.rows_table, left_columns=(0, 1, 2, 3))
        splitter.addWidget(self.rows_table)

        editor = QWidget()
        ev = QVBoxLayout(editor)
        ev.setContentsMargins(0, 8, 0, 0)
        ev.setSpacing(6)
        self.editor_key = QLabel("Выберите строку в таблице")
        self.editor_key.setProperty("role", "h2")
        ev.addWidget(self.editor_key)

        cols = QHBoxLayout()
        cols.setSpacing(10)
        self.col_base = self._editor_column("Источник при переводе")
        self.col_now = self._editor_column("Источник сейчас")
        self.col_target = self._editor_column("Ваш перевод", editable=True)
        for c in (self.col_base, self.col_now, self.col_target):
            cols.addWidget(c["box"], stretch=1)
        ev.addLayout(cols, stretch=1)

        bottom = QHBoxLayout()
        self.token_state = QLabel()
        bottom.addWidget(self.token_state, stretch=1)
        self.btn_save = QPushButton("Сохранить как проверенный")
        self.btn_save.setProperty("accent", "true")
        self.btn_save.clicked.connect(self.save_current_row)
        self.btn_save.setEnabled(False)
        bottom.addWidget(self.btn_save)
        b_next = QPushButton("Сохранить и следующая  (Ctrl+Enter)")
        b_next.clicked.connect(lambda: self.save_current_row(next_row=True))
        bottom.addWidget(b_next)
        ev.addLayout(bottom)
        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        v.addWidget(splitter, stretch=1)

        QShortcut(QKeySequence("Ctrl+Return"), self,
                  activated=lambda: self.save_current_row(next_row=True))
        return w

    def _editor_column(self, caption: str, editable: bool = False) -> dict:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        lab = QLabel(caption)
        lab.setProperty("role", "dim")
        v.addWidget(lab)
        text = QTextEdit()
        text.setReadOnly(not editable)
        text.setMinimumHeight(90)
        if editable:
            text.textChanged.connect(self._validate_editor)
        v.addWidget(text, stretch=1)
        return {"box": box, "text": text, "label": lab}

    # ---------- вкладки «Изменения» и «Диагностика» ----------

    def _build_changes(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        self.changes = QPlainTextEdit()
        self.changes.setReadOnly(True)
        v.addWidget(self.changes)
        return w

    def _build_diag(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        self.diag = QPlainTextEdit()
        self.diag.setReadOnly(True)
        v.addWidget(self.diag)
        return w

    # ---------- загрузка ----------

    def load(self, mod_id: str, mod_dir: Path | None = None) -> bool:
        self.mod_id = mod_id
        self._mod_dir = mod_dir
        cfg = settings.load()
        self.ctx = load_project_context(
            self.conn, mod_id, cfg["source_lang"], cfg["target_lang"],
            mod_dir=mod_dir,
        )
        if self.ctx is None:
            QMessageBox.warning(self, "Мод не найден",
                                f"Мод {mod_id} не найден в мастерской.")
            return False
        self.refresh()
        return True

    def reload(self):
        if self.mod_id:
            cfg = settings.load()
            self.ctx = load_project_context(
                self.conn, self.mod_id, cfg["source_lang"], cfg["target_lang"],
                mod_dir=getattr(self, "_mod_dir", None),
            )
            self.refresh()

    def refresh(self):
        ctx = self.ctx
        if ctx is None:
            return
        scan = ctx.scan
        d = scan.descriptor
        self.title.setText(scan.name)
        src = ctx.project["source_lang"]
        tgt = ctx.project["target_lang"]
        translated, of = scan.coverage(tgt, src)
        cov = f"{100 * translated / of:.1f}%" if of else "—"
        langs = ", ".join(
            f"{l} ({s.key_count})" for l, s in sorted(scan.languages.items())
        )
        counts: dict[str, int] = {}
        for r in ctx.rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        c = palette(self.theme)
        chips = "  ".join(
            f"<span style='color:{status_color(s, self.theme)}'>"
            f"{status_label(s)}: {n}</span>"
            for s, n in sorted(counts.items(), key=lambda kv: -kv[1])
        )
        self.info.setText(
            f"<span style='color:{c['text_dim']}'>ID {scan.mod_id} · "
            f"версия автора {d.version or '—'} · "
            f"совместимость {d.supported_version or '—'}</span><br>"
            f"<span style='color:{c['text_dim']}'>{scan.mod_dir}</span><br><br>"
            f"<b>Языки:</b> {langs or '—'}<br>"
            f"<b>Источник:</b> {src} → <b>цель:</b> {tgt} · "
            f"<b>покрытие:</b> {cov}<br><br>{chips}"
        )
        idx = 0 if ctx.project["write_mode"] == "in_mod" else 1
        self.write_mode.blockSignals(True)
        self.write_mode.setCurrentIndex(idx)
        self.write_mode.blockSignals(False)

        self.refresh_rows()

        diags = [
            f"[{diag.severity}] {rel}:{diag.lineno}  {diag.code}: {diag.message}"
            for rel, diag in scan.diagnostics
        ]
        self.diag.setPlainText(
            "\n".join(diags) if diags else "Проблем в файлах мода не найдено."
        )
        self.tabs.setTabText(3, f"Диагностика ({len(diags)})" if diags
                             else "Диагностика")
        self._load_changes()

    def _load_changes(self):
        snaps = self.conn.execute(
            "SELECT * FROM mod_snapshots WHERE mod_id=? ORDER BY id DESC LIMIT 6",
            (self.mod_id,),
        ).fetchall()
        if len(snaps) < 2:
            self.changes.setPlainText(
                "Изменений пока не зафиксировано.\n\n"
                "Первый снимок локализации — точка отсчёта. Когда автор мода "
                "выпустит обновление, здесь появится список новых, изменённых "
                "и удалённых строк."
            )
            return
        from ck3loc.core.store import diff_snapshots, snapshot_language

        out = []
        for new, old in zip(snaps, snaps[1:]):
            out.append(f"=== {old['taken_at']} → {new['taken_at']} ===")
            langs = self.conn.execute(
                "SELECT DISTINCT language FROM snapshot_entries WHERE snapshot_id=?",
                (new["id"],),
            ).fetchall()
            any_change = False
            for lr in langs:
                lang = lr["language"]
                diff = diff_snapshots(self.conn, old["id"], new["id"], lang)
                if diff.empty:
                    continue
                any_change = True
                out.append(
                    f"[{lang}] новых {len(diff.added)}, изменённых "
                    f"{len(diff.changed)}, удалённых {len(diff.removed)}"
                )
                newvals = snapshot_language(self.conn, new["id"], lang)
                oldvals = snapshot_language(self.conn, old["id"], lang)
                for k in diff.added[:8]:
                    out.append(f"  + {k}: \"{newvals[k]['value'][:70]}\"")
                for k in diff.changed[:8]:
                    out.append(f"  ~ {k}")
                    out.append(f"      было:  \"{oldvals[k]['value'][:70]}\"")
                    out.append(f"      стало: \"{newvals[k]['value'][:70]}\"")
                for k in diff.removed[:8]:
                    out.append(f"  − {k}")
            if not any_change:
                out.append("  локализация не менялась")
            out.append("")
        self.changes.setPlainText("\n".join(out))

    def refresh_rows(self):
        if self.ctx is None:
            return
        want = ROW_FILTERS[self.row_filter.currentText()]
        query = self.row_search.text().strip().lower()
        shown = []
        for r in self.ctx.rows:
            if want is not None and r.status not in want:
                continue
            if query and query not in r.key.lower() and \
                    query not in (r.source_text or "").lower() and \
                    query not in (r.target_text or "").lower():
                continue
            shown.append(r)
        self._shown_rows = shown
        self.rows_count.setText(f"показано {len(shown)} из {len(self.ctx.rows)}")
        self.rows_table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            st = QTableWidgetItem(status_label(r.status))
            st.setForeground(QColor(status_color(r.status, self.theme)))
            self.rows_table.setItem(i, 0, st)
            self.rows_table.setItem(i, 1, QTableWidgetItem(r.key))
            self.rows_table.setItem(
                i, 2, QTableWidgetItem((r.source_text or "")[:300])
            )
            tgt = r.target_text or r.native_target or ""
            item = QTableWidgetItem(tgt[:300])
            if r.same_as_source and tgt:
                item.setForeground(QColor(palette(self.theme)["warn"]))
                item.setToolTip("Перевод совпадает с оригиналом — проверьте")
            self.rows_table.setItem(i, 3, item)
        self.tabs.setTabText(1, f"Строки ({len(self.ctx.rows)})")

    # ---------- редактор ----------

    def _current_row(self):
        i = self.rows_table.currentRow()
        if 0 <= i < len(self._shown_rows):
            return self._shown_rows[i]
        return None

    def _load_editor(self):
        row = self._current_row()
        if row is None:
            return
        self.editor_key.setText(row.key)
        base = row.baseline_source or ""
        self.col_base["text"].setPlainText(base)
        self.col_base["box"].setVisible(bool(base) and base != row.source_text)
        self.col_now["text"].setPlainText(row.source_text or "")
        self.col_target["text"].blockSignals(True)
        self.col_target["text"].setPlainText(
            row.target_text or row.native_target or ""
        )
        self.col_target["text"].blockSignals(False)
        self.btn_save.setEnabled(row.source_text is not None)
        self._validate_editor()

    def _validate_editor(self):
        row = self._current_row()
        if row is None or row.source_text is None:
            self.token_state.setText("")
            return
        target = self.col_target["text"].toPlainText()
        c = palette(self.theme)
        if not target.strip():
            self.token_state.setText(
                f"<span style='color:{c['text_dim']}'>перевод пуст</span>"
            )
            return
        errors = validate_translation(row.source_text, target)
        if errors:
            self.token_state.setText(
                f"<span style='color:{c['err']}'>Игровые коды: "
                + "; ".join(errors[:2]) + "</span>"
            )
        else:
            self.token_state.setText(
                f"<span style='color:{c['ok']}'>Игровые коды в порядке</span>"
            )

    def save_current_row(self, next_row: bool = False):
        row = self._current_row()
        if row is None or row.source_text is None:
            return
        text = self.col_target["text"].toPlainText().strip()
        if not text:
            return
        errors = validate_translation(row.source_text, text)
        if errors:
            answer = QMessageBox.question(
                self, "Игровые коды повреждены",
                "В переводе нарушены игровые коды:\n  " + "\n  ".join(errors)
                + "\n\nСохранить всё равно? (в игру такая строка не попадёт)",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        upsert_unit(
            self.conn, self.ctx.project_id, row.key, row.source_text,
            semantic_hash(row.source_text), text, REVIEWED, "manual",
        )
        self.conn.commit()
        current_index = self.rows_table.currentRow()
        self.reload()
        if next_row and current_index + 1 < self.rows_table.rowCount():
            self.rows_table.selectRow(current_index + 1)
        elif current_index < self.rows_table.rowCount():
            self.rows_table.selectRow(current_index)

    # ---------- действия ----------

    def _log(self, text: str):
        self.log.appendPlainText(text)

    def _change_write_mode(self):
        mode = self.write_mode.currentData()
        if self.ctx is None or mode == self.ctx.project["write_mode"]:
            return
        n = self.conn.execute(
            "SELECT COUNT(*) AS n FROM generated_outputs WHERE project_id=?",
            (self.ctx.project_id,),
        ).fetchone()["n"]
        if n:
            answer = QMessageBox.question(
                self, "Смена режима записи",
                "Файлы, записанные в прежнем режиме, будут удалены "
                "(с резервными копиями), чтобы перевод не задвоился.\nПродолжить?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                idx = 0 if self.ctx.project["write_mode"] == "in_mod" else 1
                self.write_mode.blockSignals(True)
                self.write_mode.setCurrentIndex(idx)
                self.write_mode.blockSignals(False)
                return
            from ck3loc.core.writer import remove_outputs

            removed = remove_outputs(self.conn, self.ctx.project_id, self.mod_id)
            self._log(f"Удалено файлов прежнего режима: {len(removed)}.")
        set_project_option(self.conn, self.ctx.project_id, "write_mode", mode)
        self.reload()
        self._log("Режим записи изменён: "
                  + ("внутрь мода" if mode == "in_mod" else "отдельный патч-мод"))

    def do_export(self):
        from ck3loc.core.bundle import export_jsonl
        from ck3loc.core.glossary_seed import load_glossary

        rows = rows_to_translate(self.ctx, "all")
        if not rows:
            QMessageBox.information(self, "Выгрузка",
                                    "Переводить нечего — всё актуально.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить файл-задание",
            f"{self.mod_id}_{self.ctx.project['target_lang']}.jsonl",
            "Файл задания (*.jsonl)",
        )
        if not path:
            return
        res = export_jsonl(
            self.conn, self.ctx.project_id, rows, Path(path),
            self.ctx.project["source_lang"], self.ctx.project["target_lang"],
            glossary=load_glossary(self.conn, self.mod_id)[:60],
        )
        self._log(
            f"Выгружено строк: {res.unit_count}\n"
            f"  задание: {res.path}\n"
            f"  инструкция для нейросети: {res.prompt_path}\n"
            f"Отдайте оба файла нейросети, затем нажмите «Загрузить перевод из файла»."
        )
        self.note.emit(f"«{self.ctx.scan.name}»: выгружено {res.unit_count} строк")

    def do_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть переведённый файл", "",
            "Переводы (*.jsonl *.xliff *.xlf);;Все файлы (*)",
        )
        if not path:
            return
        p = Path(path)
        report = (import_xliff(self.conn, p, self.ctx.source_values)
                  if p.suffix.lower() in (".xliff", ".xlf")
                  else import_jsonl(self.conn, p, self.ctx.source_values))
        if not report.ok:
            QMessageBox.warning(self, "Загрузка остановлена", report.fatal)
            self._log(f"Загрузка остановлена: {report.fatal}")
            return
        n = apply_import_report(self.ctx, report)
        self._log(f"Принято строк: {n}, отклонено: {len(report.rejected)}")
        for r in report.rejected[:15]:
            self._log(f"   ✗ {r.key}: {r.reason}")
        self.note.emit(
            f"«{self.ctx.scan.name}»: принято {n}, отклонено {len(report.rejected)}"
        )
        self.reload()

    def do_write(self):
        plan = build_write_plan(self.ctx.scan, self.ctx.project, self.ctx.units)
        if plan.total_keys == 0:
            QMessageBox.information(
                self, "Запись",
                "Записывать нечего: готовых переводов пока нет.\n"
                "Сначала переведите строки любым способом.",
            )
            return
        files = "\n".join(f"   {f.abs_path}" for f in plan.files[:12])
        more = ("\n   …" if len(plan.files) > 12 else "")
        skipped = (f"\n\nПропущено строк: {len(plan.skipped_keys)} "
                   f"(повреждённые коды и осиротевшие)"
                   if plan.skipped_keys else "")
        answer = QMessageBox.question(
            self, "Записать перевод?",
            f"Режим: {'внутрь мода' if plan.write_mode == 'in_mod' else 'патч-мод'}"
            f", сборка: {plan.build_mode}.\nКлючей: {plan.total_keys}.\n\n"
            f"Файлы:\n{files}{more}{skipped}\n\nПродолжить?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = apply_write_plan(self.conn, self.ctx.project_id, plan,
                                  self.ctx.scan, self.ctx.units)
        self._log(f"Записано файлов: {len(result.written)}, "
                  f"ключей: {plan.total_keys}")
        if plan.write_mode == "patch_mod":
            self._log("Включите патч-мод в плейсете ПОСЛЕ оригинального мода.")
        self.note.emit(f"«{self.ctx.scan.name}»: перевод записан "
                       f"({plan.total_keys} строк)")
        self.reload()

    def do_verify(self):
        checks = verify_outputs(self.conn, self.ctx.project_id)
        if not checks:
            QMessageBox.information(
                self, "Проверка",
                "Для этого мода приложение ещё ничего не записывало.")
            return
        marks = {"ok": "✓", "missing": "✗ стёрт", "modified": "! изменён извне"}
        for c in checks:
            self._log(f"{marks[c.state]}  {c.path}")
        bad = [c for c in checks if c.state != "ok"]
        if not bad:
            QMessageBox.information(self, "Проверка",
                                    "Все записанные файлы на месте и не изменены.")
            return
        answer = QMessageBox.question(
            self, "Восстановление",
            f"Проблемных файлов: {len(bad)}.\n"
            f"Обычно это значит, что Steam обновил мод и стёр перевод.\n\n"
            f"Восстановить перевод из базы?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            plan = build_write_plan(self.ctx.scan, self.ctx.project, self.ctx.units)
            apply_write_plan(self.conn, self.ctx.project_id, plan,
                             self.ctx.scan, self.ctx.units)
            self._log(f"Восстановлено из базы: {plan.total_keys} строк.")
            self.note.emit(f"«{self.ctx.scan.name}»: перевод восстановлен")
            self.reload()

    def close_db(self):
        self.conn.close()
