"""Карточка мода: обзор, строки, диагностика, экспорт/импорт, запись."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import db
from ck3loc.core.bundle import export_jsonl, import_jsonl
from ck3loc.core.ops import (
    apply_import_report,
    load_project_context,
    rows_to_translate,
)
from ck3loc.core.scanner import semantic_hash
from ck3loc.core.status import REVIEWED
from ck3loc.core.store import set_project_option, upsert_unit
from ck3loc.core.writer import apply_write_plan, build_write_plan, verify_outputs
from ck3loc.core.xliff import import_xliff

STATUS_LABELS = {
    "missing": "Не переведено",
    "machine": "Машинный (не проверен)",
    "reviewed": "Проверено",
    "approved": "Утверждено",
    "stale": "Устарело",
    "conflict": "Конфликт",
    "orphan": "Осиротело",
    "extra": "Только в русском",
    "native": "Родной перевод мода",
    "edited_outside": "Правлено извне",
}


class ModDialog(QDialog):
    note = Signal(str)

    def __init__(self, mod_id: str, parent=None):
        super().__init__(parent)
        self.mod_id = mod_id
        self.conn = db.connect()
        self.ctx = load_project_context(self.conn, mod_id)
        if self.ctx is None:
            raise RuntimeError(f"Мод {mod_id} не найден в мастерской.")
        self.setWindowTitle(f"{self.ctx.scan.name} — {mod_id}")
        self.resize(1000, 650)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "Обзор")
        self.tabs.addTab(self._build_rows_tab(), "Строки")
        self.tabs.addTab(self._build_diag_tab(), "Диагностика")
        layout.addWidget(self.tabs)

        self.refresh()

    # ---------- вкладки ----------

    def _build_overview(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.info = QLabel()
        self.info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.info.setWordWrap(True)
        v.addWidget(self.info)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Режим записи:"))
        self.write_mode = QComboBox()
        self.write_mode.addItem("Внутрь мода (по умолчанию)", "in_mod")
        self.write_mode.addItem("Отдельный патч-мод", "patch_mod")
        idx = 0 if self.ctx.project["write_mode"] == "in_mod" else 1
        self.write_mode.setCurrentIndex(idx)
        self.write_mode.currentIndexChanged.connect(self._save_write_mode)
        opts.addWidget(self.write_mode)
        opts.addStretch(1)
        v.addLayout(opts)

        btns = QHBoxLayout()
        b_exp = QPushButton("Экспорт задания для LLM…")
        b_exp.clicked.connect(self.do_export)
        btns.addWidget(b_exp)
        b_imp = QPushButton("Импорт перевода…")
        b_imp.clicked.connect(self.do_import)
        btns.addWidget(b_imp)
        b_api = QPushButton("Перевести через API…")
        b_api.clicked.connect(self.do_api_translate)
        btns.addWidget(b_api)
        b_write = QPushButton("Записать перевод")
        b_write.clicked.connect(self.do_write)
        btns.addWidget(b_write)
        b_verify = QPushButton("Проверить/восстановить")
        b_verify.clicked.connect(self.do_verify)
        btns.addWidget(b_verify)
        v.addLayout(btns)

        self.overview_log = QPlainTextEdit()
        self.overview_log.setReadOnly(True)
        v.addWidget(self.overview_log, stretch=1)
        return w

    def _build_rows_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("Показать:"))
        self.row_filter = QComboBox()
        self.row_filter.addItems(
            ["Все", "Не переведено", "Устарело", "Машинные", "Конфликты",
             "Только в русском", "Родной перевод"]
        )
        self.row_filter.currentIndexChanged.connect(self.refresh_rows)
        top.addWidget(self.row_filter)
        top.addStretch(1)
        hint = QLabel("Двойной клик по строке — редактировать перевод")
        top.addWidget(hint)
        v.addLayout(top)

        self.rows_table = QTableWidget(0, 4)
        self.rows_table.setHorizontalHeaderLabels(
            ["Статус", "Ключ", "Источник", "Перевод"]
        )
        self.rows_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.rows_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.rows_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rows_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.rows_table.doubleClicked.connect(self.edit_row)
        v.addWidget(self.rows_table, stretch=1)
        return w

    def _build_diag_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.diag = QPlainTextEdit()
        self.diag.setReadOnly(True)
        v.addWidget(self.diag)
        return w

    # ---------- данные ----------

    def reload_ctx(self):
        self.ctx = load_project_context(self.conn, self.mod_id)

    def refresh(self):
        ctx = self.ctx
        scan = ctx.scan
        d = scan.descriptor
        langs = ", ".join(
            f"{l} ({s.key_count})" for l, s in sorted(scan.languages.items())
        )
        src = ctx.project["source_lang"]
        translated, of = scan.coverage(ctx.project["target_lang"], src)
        cov = f"{100 * translated / of:.1f}%" if of else "—"
        counts: dict[str, int] = {}
        for r in ctx.rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        status_line = " · ".join(
            f"{STATUS_LABELS.get(s, s)}: {n}" for s, n in sorted(counts.items())
        )
        self.info.setText(
            f"<b>{scan.name}</b> (ID {scan.mod_id})<br>"
            f"Папка: {scan.mod_dir}<br>"
            f"Версия автора: {d.version or '—'} · "
            f"Совместимость: {d.supported_version or '—'}<br>"
            f"Языки: {langs or '—'}<br>"
            f"Источник: {src} · Русское покрытие: {cov}<br>"
            f"{status_line}"
        )
        self.refresh_rows()
        diags = [
            f"[{diag.severity}] {rel}:{diag.lineno} {diag.code}: {diag.message}"
            for rel, diag in ctx.scan.diagnostics
        ]
        self.diag.setPlainText(
            "\n".join(diags) if diags else "Проблем не найдено."
        )

    def refresh_rows(self):
        mode = self.row_filter.currentText()
        want = {
            "Все": None,
            "Не переведено": {"missing"},
            "Устарело": {"stale"},
            "Машинные": {"machine"},
            "Конфликты": {"conflict", "edited_outside"},
            "Только в русском": {"extra", "orphan"},
            "Родной перевод": {"native"},
        }[mode]
        shown = [
            r for r in self.ctx.rows if want is None or r.status in want
        ]
        self.rows_table.setRowCount(len(shown))
        self._shown_rows = shown
        for i, r in enumerate(shown):
            vals = [
                STATUS_LABELS.get(r.status, r.status),
                r.key,
                (r.source_text or "")[:200],
                (r.target_text or r.native_target or "")[:200],
            ]
            for col, text in enumerate(vals):
                self.rows_table.setItem(i, col, QTableWidgetItem(text))

    # ---------- действия ----------

    def _save_write_mode(self):
        mode = self.write_mode.currentData()
        set_project_option(self.conn, self.ctx.project_id, "write_mode", mode)
        self.ctx.project["write_mode"] = mode

    def do_export(self):
        rows = rows_to_translate(self.ctx, "all")
        if not rows:
            QMessageBox.information(
                self, "Экспорт", "Строк для перевода нет — всё актуально."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить файл-задание",
            f"{self.mod_id}_russian.jsonl", "JSONL (*.jsonl)",
        )
        if not path:
            return
        res = export_jsonl(
            self.conn, self.ctx.project_id, rows, Path(path),
            self.ctx.project["source_lang"], self.ctx.project["target_lang"],
        )
        self.overview_log.appendPlainText(
            f"Экспортировано {res.unit_count} строк → {res.path}\n"
            f"Промпт для LLM: {res.prompt_path}\n"
            f"Отдайте оба файла любой нейросети, затем нажмите «Импорт перевода»."
        )
        self.note.emit(f"«{self.ctx.scan.name}»: экспортировано {res.unit_count} строк.")

    def do_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть переведённый файл", "",
            "Переводы (*.jsonl *.xliff *.xlf)",
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() in (".xliff", ".xlf"):
            report = import_xliff(self.conn, p, self.ctx.source_values)
        else:
            report = import_jsonl(self.conn, p, self.ctx.source_values)
        if not report.ok:
            QMessageBox.warning(self, "Импорт остановлен", report.fatal)
            return
        n = apply_import_report(self.ctx, report)
        msg = f"Принято строк: {n}."
        if report.rejected:
            details = "\n".join(
                f"  {r.key}: {r.reason}" for r in report.rejected[:10]
            )
            msg += f"\nОтклонено: {len(report.rejected)}:\n{details}"
        self.overview_log.appendPlainText(msg)
        self.note.emit(f"«{self.ctx.scan.name}»: импорт — принято {n}, "
                       f"отклонено {len(report.rejected)}.")
        self.reload_ctx()
        self.refresh()

    def do_api_translate(self):
        from ck3loc.core.pipeline import build_vanilla_lookup, estimate
        from ck3loc.desktop.translate_dialog import TranslateDialog

        rows = rows_to_translate(self.ctx, "all")
        if not rows:
            QMessageBox.information(
                self, "Перевод", "Переводить нечего — всё актуально."
            )
            return
        vl = build_vanilla_lookup(
            self.ctx.project["source_lang"], self.ctx.project["target_lang"]
        )
        est = estimate(self.ctx, rows, vanilla_lookup=vl)
        text = (
            f"Строк на перевод: {est.rows}\n"
            f"Закроется ванилью CK3 (бесплатно): {est.covered_by_vanilla}\n"
            f"Закроется памятью переводов (бесплатно): {est.covered_by_memory}\n"
            f"Пойдёт в API: {est.rows - est.covered_by_vanilla - est.covered_by_memory} "
            f"строк, ~{est.chars_to_api} символов"
        )
        dlg = TranslateDialog(self.mod_id, text, parent=self)
        dlg.exec()
        if dlg.stats is not None:
            self.note.emit(
                f"«{self.ctx.scan.name}»: переведено {dlg.stats.translated} строк."
            )
        self.reload_ctx()
        self.refresh()

    def do_write(self):
        plan = build_write_plan(self.ctx.scan, self.ctx.project, self.ctx.units)
        if plan.total_keys == 0:
            QMessageBox.information(
                self, "Запись", "Записывать нечего: нет готовых переводов."
            )
            return
        files = "\n".join(f"  {f.abs_path}" for f in plan.files)
        skipped = ""
        if plan.skipped_keys:
            skipped = f"\n\nПропущено строк: {len(plan.skipped_keys)} (ошибки кодов и осиротевшие)"
        answer = QMessageBox.question(
            self, "Записать перевод?",
            f"Режим: {'внутрь мода' if plan.write_mode == 'in_mod' else 'патч-мод'}, "
            f"сборка: {plan.build_mode}.\n"
            f"Ключей: {plan.total_keys}. Файлы:\n{files}{skipped}\n\nПродолжить?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = apply_write_plan(
            self.conn, self.ctx.project_id, plan, self.ctx.scan, self.ctx.units
        )
        msg = f"Записано файлов: {len(result.written)}."
        if plan.write_mode == "patch_mod":
            msg += "\nВключите патч-мод в плейсете ПОСЛЕ оригинального мода."
        self.overview_log.appendPlainText(msg)
        self.note.emit(f"«{self.ctx.scan.name}»: перевод записан "
                       f"({plan.total_keys} ключей).")
        self.reload_ctx()
        self.refresh()

    def do_verify(self):
        checks = verify_outputs(self.conn, self.ctx.project_id)
        if not checks:
            QMessageBox.information(
                self, "Проверка", "Приложение ещё ничего не записывало для этого мода."
            )
            return
        bad = [c for c in checks if c.state != "ok"]
        lines = []
        for c in checks:
            mark = {"ok": "✓", "missing": "✗ стёрт",
                    "modified": "! изменён извне"}[c.state]
            lines.append(f"{mark}  {c.path}")
        self.overview_log.appendPlainText("\n".join(lines))
        if not bad:
            QMessageBox.information(self, "Проверка",
                                    "Все записанные файлы на месте.")
            return
        answer = QMessageBox.question(
            self, "Восстановление",
            f"Проблемных файлов: {len(bad)} (стёрты обновлением Steam или "
            f"изменены вручную).\nВосстановить из базы?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            plan = build_write_plan(self.ctx.scan, self.ctx.project, self.ctx.units)
            apply_write_plan(self.conn, self.ctx.project_id, plan,
                             self.ctx.scan, self.ctx.units)
            self.overview_log.appendPlainText("Восстановлено из базы.")
            self.note.emit(f"«{self.ctx.scan.name}»: перевод восстановлен.")

    def edit_row(self):
        i = self.rows_table.currentRow()
        if i < 0 or i >= len(self._shown_rows):
            return
        row = self._shown_rows[i]
        if row.source_text is None:
            QMessageBox.information(
                self, "Редактирование",
                "У этой строки нет источника (осиротевшая или только в русском) — "
                "редактирование не требуется.",
            )
            return
        dlg = _EditDialog(row, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = dlg.result_text()
            if not new_text.strip():
                return
            upsert_unit(
                self.conn, self.ctx.project_id, row.key, row.source_text,
                semantic_hash(row.source_text), new_text, REVIEWED, "manual",
            )
            self.conn.commit()
            self.note.emit(f"«{self.ctx.scan.name}»: {row.key} отредактирован.")
            self.reload_ctx()
            self.refresh()

    def closeEvent(self, event):
        self.conn.close()
        super().closeEvent(event)


class _EditDialog(QDialog):
    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Строка {row.key}")
        self.resize(700, 400)
        v = QVBoxLayout(self)
        if row.baseline_source and row.baseline_source != row.source_text:
            v.addWidget(QLabel("<b>Источник при переводе:</b>"))
            old = QTextEdit()
            old.setReadOnly(True)
            old.setPlainText(row.baseline_source)
            old.setMaximumHeight(80)
            v.addWidget(old)
        v.addWidget(QLabel("<b>Источник сейчас:</b>"))
        src = QTextEdit()
        src.setReadOnly(True)
        src.setPlainText(row.source_text or "")
        src.setMaximumHeight(80)
        v.addWidget(src)
        v.addWidget(QLabel("<b>Перевод:</b>"))
        self.editor = QTextEdit()
        self.editor.setPlainText(row.target_text or row.native_target or "")
        v.addWidget(self.editor, stretch=1)
        btns = QHBoxLayout()
        ok = QPushButton("Сохранить (проверено)")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        v.addLayout(btns)

    def result_text(self) -> str:
        return self.editor.toPlainText()
