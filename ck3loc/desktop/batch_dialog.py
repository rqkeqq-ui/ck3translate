"""Массовый мастер: моды без перевода, выгрузка для LLM, перевод, импорт и запись.

Окно открывается сразу: список модов собирается в фоне с прогрессом, а
выгрузка, импорт и подготовка записи тоже идут в фоновых задачах. Мастер сам
ничего не отправляет и не записывает: каждое действие — отдельная кнопка с
предпросмотром.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ck3loc.core import db, settings
from ck3loc.core.i18n import tr, tr_format
from ck3loc.desktop.review_dialog import ReviewDialog
from ck3loc.desktop.tasks import ConfirmDialog, Task


@dataclass
class Candidate:
    """Лёгкое описание мода для мастера (без соединения с базой)."""

    mod_id: str
    path: Path
    source: str
    name: str
    source_lang: str
    target_lang: str
    project_id: int
    rows: list[dict] = field(default_factory=list)  # недостающие строки
    missing_files: bool = False
    unwritten: int = 0  # применено в базе, но ещё не записано в игру


def load_candidates(conn, report, token) -> list[Candidate]:
    from ck3loc.core.mod_library import discover_mods
    from ck3loc.core.ops import load_project_context, rows_to_translate
    from ck3loc.core.writer import verify_outputs

    cfg = settings.load()
    mods = discover_mods().mods
    result = []
    for i, mod in enumerate(mods, 1):
        if token.cancelled:
            break
        report(i, len(mods), mod.path.name)
        ctx = load_project_context(conn, mod.mod_id, cfg['source_lang'], cfg['target_lang'], mod_dir=mod.path)
        if ctx is None:
            continue
        lost = any(c.state == 'missing' for c in verify_outputs(conn, ctx.project_id))
        rows = rows_to_translate(ctx, 'missing')
        unwritten = pending_write_count(ctx)
        if lost or rows or unwritten:
            result.append(Candidate(mod.mod_id, mod.path, 'Local' if mod.source == 'local' else 'Workshop',
                                    ctx.scan.name, ctx.project['source_lang'], ctx.project['target_lang'],
                                    ctx.project_id, rows, lost, unwritten))
    return result


def pending_write_count(ctx) -> int:
    """Сколько применённых строк ещё не записано в игру (или изменено после записи)."""
    from ck3loc.core.scanner import semantic_hash
    count = 0
    for key, raw in ctx.units.items():
        unit = dict(raw)
        target = unit.get('target_text') or ''
        if target and key in ctx.source_values and unit.get('target_hash_written') != semantic_hash(target):
            count += 1
    return count


def part_sizes(rows: list[dict], fmt: str, part_size: int | None) -> list[int]:
    """Те же части, что построит plan_export: YML учитывает границы исходных файлов."""
    groups: dict[str, int] = {}
    for row in rows:
        group = row.get('rel_path', '') if fmt == 'yml' else ''
        groups[group] = groups.get(group, 0) + 1
    sizes = []
    for _group, count in sorted(groups.items()):
        limit = part_size or count
        sizes.extend(min(limit, count - i) for i in range(0, count, limit))
    return sizes


def review_and_apply(parent, staged: list[dict]) -> dict[str, int] | None:
    """Один общий предпросмотр на все моды; применение выбранного в фоне.

    staged: [{name, mod_id, mod_dir, source_lang, target_lang, job_id, preview}].
    Возвращает {job_id: применено строк} или None, если пользователь отменил.
    """
    from dataclasses import replace
    from ck3loc.desktop.tasks import run_with_progress
    if all(row.change == 'unchanged' for item in staged for row in item['preview']):
        return {}  # повторная загрузка того же результата: менять нечего, окно не нужно
    names = [item['name'] for item in staged]
    rows, owners = [], {}
    for item in staged:
        label = item['name'] if names.count(item['name']) == 1 else f"{item['name']} #{item['job_id'][:6]}"
        for row in item['preview']:
            shown = f'{label} › {row.key}'
            owners[shown] = (item, row.key)
            rows.append(replace(row, key=shown))
    dialog = ReviewDialog(rows, tr_format('Предпросмотр: {n} модов', n=len(staged)), parent=parent,
                          groups={shown: owners[shown][0]['name'] for shown in owners},
                          display_keys={shown: owners[shown][1] for shown in owners})
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    chosen: dict[str, set[str]] = {}
    for shown in dialog.selected_keys():
        item, key = owners[shown]
        chosen.setdefault(item['job_id'], set()).add(key)

    def work(conn, report, token):
        from ck3loc.core.jobs import apply_job
        from ck3loc.core.ops import load_project_context
        result = {}
        targets = [item for item in staged if item['job_id'] in chosen]
        for i, item in enumerate(targets, 1):
            report(i, len(targets), item['name'])
            ctx = load_project_context(conn, item['mod_id'], item['source_lang'], item['target_lang'],
                                       mod_dir=item['mod_dir'])
            if ctx is not None:
                result[item['job_id']] = len(apply_job(ctx, item['job_id'], chosen[item['job_id']]).changed)
        return result

    result, error = run_with_progress(parent, tr('Применяю выбранные строки…'), work)
    if error:
        QMessageBox.warning(parent, tr('Массовый перевод'), error)
        return {}
    return result


def _context(conn, cand: Candidate):
    from ck3loc.core.ops import load_project_context
    return load_project_context(conn, cand.mod_id, cand.source_lang, cand.target_lang, mod_dir=cand.path)


class BatchDialog(QDialog):
    def __init__(self, parent=None, *, synchronous: bool = False):
        super().__init__(parent)
        self.conn = db.connect()
        self.synchronous = synchronous
        self.task = None
        self.candidates: list[Candidate] = []
        self.key_selections: dict[int, set[str]] = {}
        self.setWindowTitle(tr('Массовый перевод'))
        self.setSizeGripEnabled(True)
        self.resize(1080, 680)
        v = QVBoxLayout(self)
        hint = QLabel(tr('Мастер ничего не отправляет и не записывает сам: выгрузка, перевод, '
                         'применение и запись в игру — отдельные шаги.'))
        hint.setWordWrap(True)
        v.addWidget(hint)

        busy = QHBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        busy.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(320)
        busy.addWidget(self.progress)
        self.cancel_task = QPushButton(tr('Остановить'))
        self.cancel_task.clicked.connect(self._cancel_task)
        busy.addWidget(self.cancel_task)
        v.addLayout(busy)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr(s) for s in ['Выбрать', 'Мод', 'Папка', 'Языки', 'Строки']])
        header = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                       QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                                       QHeaderView.ResizeMode.ResizeToContents)):
            header.setSectionResizeMode(column, mode)
        self.table.setWordWrap(False)
        self.table.itemChanged.connect(self.update_preview)
        v.addWidget(self.table, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr('Формат:')))
        self.format = QComboBox()
        for fmt in ('jsonl', 'xliff', 'yml'):
            self.format.addItem(fmt.upper(), fmt)
        row.addWidget(self.format)
        from ck3loc.desktop.tasks import SplitControl
        self.splitter = SplitControl()
        row.addWidget(self.splitter)
        self.choose = QPushButton(tr('Выбрать строки'))
        self.choose.setToolTip(tr('Выберите мод в таблице, затем отметьте строки внутри него.'))
        self.choose.clicked.connect(self.choose_keys)
        row.addWidget(self.choose)
        row.addStretch(1)
        v.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        for signal in (self.format.currentIndexChanged, self.splitter.changed):
            signal.connect(self.update_preview)

        actions = QHBoxLayout()
        self.action_buttons = []
        for title, callback in [('Выгрузить для LLM', self.export),
                                ('Перевести через подписку ChatGPT или сервис…', self.translate),
                                ('Загрузить результаты LLM…', self.import_results),
                                ('Загрузить папку результатов…', self.import_directory),
                                ('Записать выбранные переводы в игру…', self.write_selected)]:
            button = QPushButton(tr(title))
            button.clicked.connect(callback)
            actions.addWidget(button)
            self.action_buttons.append(button)
        v.addLayout(actions)
        close = QPushButton(tr('Закрыть'))
        close.clicked.connect(self.reject)
        v.addWidget(close)
        self.finished.connect(self._cleanup)
        self._set_busy(False)
        self.reload()

    # ---------- фоновые задачи ----------

    def _set_busy(self, busy: bool, text: str = '') -> None:
        for button in self.action_buttons + [self.choose]:
            button.setEnabled(not busy and bool(self.candidates))
        self.table.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.cancel_task.setVisible(busy)
        if text:
            self.status.setText(text)

    def run_task(self, fn, on_success, busy_text: str) -> None:
        if self.synchronous:  # тесты: тот же код без потока
            from ck3loc.core.jobs import CancellationToken
            on_success(fn(self.conn, lambda *_: None, CancellationToken()))
            return
        self._set_busy(True, busy_text)
        self.progress.setRange(0, 0)
        task = Task(fn, self)
        self.task = task

        def progress(i, total, text):
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(i)
            self.status.setText(f'{busy_text} {i}/{total} · {text}')

        def finished_ok(result):
            self.task = None
            self._set_busy(False, '')
            on_success(result)

        def finished_error(error):
            self.task = None
            self._set_busy(False, tr_format('Ошибка: {error}', error=error))
            QMessageBox.warning(self, tr('Массовый перевод'), error)

        task.progress.connect(progress)
        task.succeeded.connect(finished_ok)
        task.failed.connect(finished_error)
        task.start()

    def _cancel_task(self):
        if self.task is not None:
            self.task.cancel()
            self.status.setText(tr('Останавливаю после текущего мода…'))

    def _cleanup(self, *_):
        if self.task is not None and self.task.isRunning():
            self.task.cancel()
            self.task.wait()
        self.conn.close()

    # ---------- список модов ----------

    def reload(self):
        self.run_task(load_candidates, self._loaded, tr('Читаю моды библиотеки…'))

    def _loaded(self, candidates):
        self.candidates = candidates
        self.key_selections = {c.project_id: {r['key'] for r in c.rows} for c in candidates}
        self.table.blockSignals(True)
        self.table.setRowCount(len(candidates))
        for i, cand in enumerate(candidates):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if cand.rows or cand.unwritten else Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, item)
            lines = str(len(cand.rows))
            if cand.unwritten:
                lines += ' · ' + tr_format('не записано в игру: {n}', n=cand.unwritten)
            if cand.missing_files:
                lines += ' · ' + tr('файлы перевода отсутствуют — восстановите записью')
            for j, text in enumerate([cand.name, f'{cand.source} · {cand.path}',
                                      f'{cand.source_lang} → {cand.target_lang}', lines], 1):
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(i, j, cell)
        self.table.blockSignals(False)
        self._set_busy(False)
        self.status.setText(tr_format('Модов, где есть что перевести или записать в игру: {n}.',
                                      n=len(candidates)) if candidates else
                            tr('Модов без перевода не найдено. Переводить нечего — всё актуально.'))
        self.update_preview()

    @property
    def contexts(self):
        """Совместимость: мастер хранит лёгкие описания модов, а не контексты."""
        return self.candidates

    def selected(self) -> list[Candidate]:
        return [c for i, c in enumerate(self.candidates)
                if self.table.item(i, 0) and self.table.item(i, 0).checkState() == Qt.CheckState.Checked]

    def _selected_rows(self, cand: Candidate) -> list[dict]:
        keys = self.key_selections.get(cand.project_id, set())
        return [r for r in cand.rows if r['key'] in keys]

    def split_kwargs(self) -> dict:
        return self.splitter.kwargs()

    def update_preview(self, *_):
        from ck3loc.core.exchange import describe_sizes, package_sizes
        if not hasattr(self, 'summary'):
            return
        total = mods = 0
        for cand in self.selected():
            rows = self._selected_rows(cand)
            if rows:
                mods += 1
                total += len(rows)
        sizes = package_sizes(total, **self.split_kwargs())
        self.summary.setText(tr_format('Выбрано модов: {mods}; строк: {n}. Выгрузка для LLM: ZIP-архивов {parts} '
                                       '({sizes} строк) и один файл с промптом. Моды внутри архива — отдельными папками.',
                                       mods=mods, n=total, parts=len(sizes), sizes=describe_sizes(sizes)))

    def choose_keys(self):
        from ck3loc.core.jobs import ChangePreview
        i = self.table.currentRow()
        if not 0 <= i < len(self.candidates):
            QMessageBox.information(self, tr('Выбрать строки'), tr('Сначала выберите мод в таблице.'))
            return
        cand = self.candidates[i]
        rows = [ChangePreview(r['key'], r['source'], r.get('current_target', ''), '', 'select') for r in cand.rows]
        dialog = ReviewDialog(rows, 'Выбрать строки', default_changes=(), action_label='Выбрать {n} строк',
                              parent=self)
        for j, r in enumerate(rows):
            dialog.table.item(j, 0).setCheckState(
                Qt.CheckState.Checked if r.key in self.key_selections[cand.project_id] else Qt.CheckState.Unchecked)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.key_selections[cand.project_id] = dialog.selected_keys()
            self.update_preview()

    # ---------- выгрузка ----------

    def export(self):
        from ck3loc.core.exchange import describe_sizes, package_sizes
        fmt, split = self.format.currentData(), self.split_kwargs()
        chosen = [(c, self._selected_rows(c)) for c in self.selected()]
        chosen = [(c, rows) for c, rows in chosen if rows]
        if not chosen:
            QMessageBox.information(self, tr('Выгрузка'), tr('Нет выбранных строк для выгрузки.'))
            return
        directory = QFileDialog.getExistingDirectory(self, tr('Куда сохранить архивы задания'))
        if not directory:
            return
        total = sum(len(rows) for _c, rows in chosen)
        sizes = package_sizes(total, **split)
        details = '\n'.join(f'{cand.name}: {len(rows)}' for cand, rows in chosen)
        summary = tr_format('Будет создано ZIP-архивов: {parts} ({sizes} строк) для {mods} модов и один файл с '
                            'промптом в папке:\n{root}', parts=len(sizes), sizes=describe_sizes(sizes),
                            mods=len(chosen), root=directory)
        if not ConfirmDialog.ask(self, 'Выгрузка', summary, details, ok_text='Выгрузить'):
            return
        selections = [(c, {r['key'] for r in rows}) for c, rows in chosen]
        import time
        name = f"ck3loc_batch_{chosen[0][0].target_lang}_{time.strftime('%Y%m%d_%H%M%S')}"

        def work(conn, report, token):
            from ck3loc.core.exchange import write_package
            from ck3loc.core.ops import rows_to_translate
            items, errors = [], []
            for i, (cand, keys) in enumerate(selections, 1):
                if token.cancelled:
                    return None, errors
                report(i, len(selections), cand.name)
                ctx = _context(conn, cand)
                if ctx is None:
                    errors.append(f"{cand.name}: {tr('мод недоступен')}")
                    continue
                items.append((ctx, rows_to_translate(ctx, 'selected', keys)))
            report(len(selections), len(selections), tr('Упаковываю архивы…'))
            return write_package(items, Path(directory), fmt, name=name, **split), errors

        def done(result):
            package, errors = result
            if package is None or self.synchronous:
                return
            listing = '\n'.join(f'{p.name} — {size}' for p, size in zip(package.archives, package.sizes))
            text = tr_format('Готово. Отправьте нейросети архивы и текст из файла {prompt}. Ответы загрузите кнопкой '
                             '«Загрузить результаты LLM…» — можно выбрать сразу все ZIP.', prompt=package.prompt.name)
            if ConfirmDialog.ask(self, 'Выгрузка', text, listing + ('\n\n' + '\n'.join(errors) if errors else ''),
                                 ok_text='Открыть папку', cancel_text='Закрыть'):
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(package.prompt.parent)))

        self.run_task(work, done, tr('Выгружаю задания…'))

    # ---------- перевод ----------

    def translate(self):
        chosen = [(c, self.key_selections.get(c.project_id, set())) for c in self.selected()]
        chosen = [(c, keys) for c, keys in chosen if keys]
        if not chosen:
            QMessageBox.information(self, tr('Массовый перевод'), tr('Нет выбранных строк для перевода.'))
            return
        BatchTranslateDialog(chosen, parent=self).exec()
        self.reload()

    # ---------- импорт ----------

    def import_directory(self):
        from ck3loc.core.exchange import result_files
        directory = QFileDialog.getExistingDirectory(self, tr('Папка результатов'))
        if directory:
            self.import_results(paths=result_files(Path(directory)))

    def import_results(self, _checked=False, *, paths=None):
        if paths is None:
            names, _ = QFileDialog.getOpenFileNames(self, tr('Открыть переведённый файл'), '',
                                                    'Translations (*.zip *.jsonl *.xliff *.xlf *.yml)')
            paths = [Path(n) for n in names]
        if not paths:
            return

        def work(conn, report, token):
            import tempfile
            from ck3loc.core.exchange import (expand_archives, import_files, package_progress, route_files,
                                              stage_import)
            temporary = tempfile.TemporaryDirectory(prefix='ck3loc_import_')
            try:
                files, errors = expand_archives(paths, Path(temporary.name))
                return _import(conn, report, token, files, errors)
            finally:
                temporary.cleanup()

        def _import(conn, report, token, files, errors):
            from ck3loc.core.exchange import import_files, package_progress, route_files, stage_import
            from ck3loc.core.jobs import preview_job
            from ck3loc.core.ops import load_project_context
            routed, route_errors = route_files(conn, files)
            errors.extend(route_errors)
            staged, exported = [], set()
            for i, (pid, files) in enumerate(routed.items(), 1):
                if token.cancelled:
                    break
                project = conn.execute('SELECT * FROM translation_projects WHERE id=?', (pid,)).fetchone()
                cand = next((c for c in self.candidates if c.project_id == pid), None)
                report(i, len(routed), cand.name if cand else project['mod_id'])
                ctx = load_project_context(conn, project['mod_id'], project['source_lang'], project['target_lang'],
                                           mod_dir=cand.path if cand else None)
                if not ctx:
                    errors.append(f"{project['mod_id']}: {tr('мод недоступен')}")
                    continue
                report_ = import_files(ctx, files)
                errors.extend(f'{ctx.scan.name}: {tr(w)}' for w in report_.warnings)
                errors.extend(f'{ctx.scan.name}: {r.key}: {tr(r.reason)}' for r in report_.rejected)
                if not report_.ok or not report_.accepted:
                    if report_.fatal:
                        errors.append(f'{ctx.scan.name}: {tr(report_.fatal)}')
                    continue
                job_id = stage_import(ctx, report_)
                exported |= {e for ids in report_.unit_exports.values() for e in ids}
                staged.append(dict(name=ctx.scan.name, mod_id=project['mod_id'], mod_dir=ctx.scan.mod_dir,
                                   source_lang=project['source_lang'], target_lang=project['target_lang'],
                                   job_id=job_id, accepted=len(report_.accepted), rejected=len(report_.rejected),
                                   preview=preview_job(ctx, job_id)))
            # Прогресс пакета считаем один раз, когда все возвращённые файлы уже учтены.
            return staged, errors, package_progress(conn, exported)

        self.run_task(work, self._review_imports, tr('Проверяю файлы результатов…'))

    def _review_imports(self, result):
        staged, errors, progress = result
        applied = review_and_apply(self, staged) if staged else None
        summary = []
        for item in staged:
            summary.append(tr_format('{mod}: принято {accepted}, отклонено {rejected}, применено {applied}',
                                     mod=item['name'], accepted=item['accepted'], rejected=item['rejected'],
                                     applied=(applied or {}).get(item['job_id'], 0)))
        for _package, received, total, missing in progress:
            summary.append(tr_format('Получено архивов: {received} из {total}; не вернулось строк: {missing}',
                                     received=received, total=total, missing=missing))
        if staged and applied is None:
            summary.append(tr('Применение отменено. Неприменённые черновики сохранены в «Истории действий» каждого мода.'))
        if summary or errors:
            footer = (tr('Игровые файлы не менялись: используйте «Записать выбранные переводы в игру…».')
                      if staged else '')
            if not self.synchronous:
                ConfirmDialog.inform(self, 'Отчёт импорта', '\n'.join(summary) + ('\n\n' + footer if footer else ''),
                                     '\n'.join(errors))
        self.reload()

    # ---------- запись ----------

    def write_selected(self):
        """Явная запись в игру: список собственных файлов, резервные копии, исключение модов."""
        chosen = self.selected()
        if not chosen:
            QMessageBox.information(self, tr('Запись'), tr('Отметьте моды в таблице.'))
            return

        def work(conn, report, token):
            from ck3loc.core.writer import build_write_plan, prepare_write_plan
            plans, errors = [], []
            for i, cand in enumerate(chosen, 1):
                if token.cancelled:
                    break
                report(i, len(chosen), cand.name)
                ctx = _context(conn, cand)
                if ctx is None:
                    errors.append(f"{cand.name}: {tr('мод недоступен')}")
                    continue
                plan = build_write_plan(ctx.scan, ctx.project, ctx.units,
                                        has_external_provider=ctx.provider is not None)
                try:
                    prepare_write_plan(conn, ctx.project_id, plan)
                except ValueError as exc:
                    errors.append(f'{ctx.scan.name}: {exc}')
                    continue
                if plan.total_keys or plan.delete_paths:
                    plans.append((ctx.scan.name, ctx.project_id, plan, ctx.scan, dict(ctx.units)))
            return plans, errors

        self.run_task(work, self._confirm_write, tr('Готовлю запись…'))

    def _confirm_write(self, result):
        plans, errors = result
        if not plans:
            QMessageBox.information(self, tr('Запись'), '\n'.join(errors)
                                    or tr('Записывать нечего: готовых переводов пока нет.'))
            return
        dialog = WritePreviewDialog(plans, errors, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dialog.chosen()

        def work(conn, report, token):
            from ck3loc.core.writer import apply_write_plan
            lines = []
            for i, (name, project_id, plan, scan, units) in enumerate(chosen, 1):
                report(i, len(chosen), name)
                try:
                    written = apply_write_plan(conn, project_id, plan, scan, units)
                    lines.append(tr_format('{mod}: записано файлов {files}, резервных копий {backups}',
                                           mod=name, files=len(written.written), backups=len(written.backups)))
                except (OSError, ValueError) as exc:
                    lines.append(f'{name}: {exc}')
            return lines

        def done(lines):
            if not self.synchronous:
                ConfirmDialog.inform(self, 'Запись', tr('Запись завершена.'), '\n'.join(lines))
            self.reload()

        self.run_task(work, done, tr('Записываю…'))


class WritePreviewDialog(QDialog):
    """Точный список собственных файлов по модам до записи; моды можно исключить."""

    def __init__(self, plans, errors, parent=None):
        super().__init__(parent)
        self.plans = plans
        self.setWindowTitle(tr('Записать выбранные переводы в игру'))
        self.setSizeGripEnabled(True)
        self.resize(980, 560)
        v = QVBoxLayout(self)
        note = QLabel(tr('Записываются только собственные файлы менеджера; файлы автора мода не меняются. '
                         'Перед заменой создаются резервные копии. Снимите галочку, чтобы исключить мод.'))
        note.setWordWrap(True)
        v.addWidget(note)
        self.table = QTableWidget(len(plans), 4)
        self.table.setHorizontalHeaderLabels([tr(s) for s in ['Записать', 'Мод', 'Строк', 'Файлы']])
        header = self.table.horizontalHeader()
        for column, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Interactive,
                                       QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            header.setSectionResizeMode(column, mode)
        self.table.setColumnWidth(1, 300)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.verticalHeader().hide()
        for i, (name, _pid, plan, _scan, _units) in enumerate(plans):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(i, 0, item)
            files = [str(f.abs_path) for f in plan.files] + ['− ' + str(p) for p in plan.delete_paths]
            shown = files[0] + (tr_format(' и ещё {n}', n=len(files) - 1) if len(files) > 1 else '') if files else ''
            for j, text in enumerate([name, str(plan.total_keys), shown], 1):
                cell = QTableWidgetItem(text)
                cell.setToolTip('\n'.join(files) if j == 3 else text)
                cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(i, j, cell)
        v.addWidget(self.table, 1)
        if errors:
            blocked = QPlainTextEdit(tr('Не будут записаны:') + '\n' + '\n'.join(errors))
            blocked.setReadOnly(True)
            blocked.setMaximumHeight(120)
            v.addWidget(blocked)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(tr('Записать'))
        ok.setProperty('accent', 'true')
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        cancel = QPushButton(tr('Отмена'))
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        v.addLayout(row)

    def chosen(self):
        return [plan for i, plan in enumerate(self.plans)
                if self.table.item(i, 0).checkState() == Qt.CheckState.Checked]


class BatchTranslateWorker(Task):
    """Перевод выбранных модов по очереди в черновики; общая остановка между запросами."""

    def __init__(self, chosen, provider_name: str, options: dict, parent=None, *, provider=None):
        super().__init__(self._work, parent)
        self.chosen, self.provider_name, self.options = chosen, provider_name, options
        self.provider = provider

    def _work(self, conn, report, token):
        from ck3loc.core.ops import rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, translate_rows
        from ck3loc.providers.registry import make_provider
        provider = self.provider or make_provider(self.provider_name)
        total = sum(len(keys) for _c, keys in self.chosen)
        done_before = 0
        results = []
        for cand, keys in self.chosen:
            if token.cancelled:
                break
            ctx = _context(conn, cand)
            if ctx is None:
                results.append(dict(name=cand.name, error=tr('мод недоступен')))
                continue
            rows = rows_to_translate(ctx, 'selected', keys)
            vanilla = (build_vanilla_lookup(cand.source_lang, cand.target_lang)
                       if self.options.get('use_vanilla') and not self.options.get('retranslate') else {})
            base = done_before
            stats = translate_rows(ctx, rows, provider, vanilla_lookup=vanilla, cancellation=token,
                                   progress_cb=lambda d, _t, b=base: report(b + d, total, cand.name),
                                   **self.options)
            done_before += len(rows)
            results.append(dict(name=cand.name, mod_id=cand.mod_id, mod_dir=cand.path,
                                source_lang=cand.source_lang, target_lang=cand.target_lang,
                                job_id=stats.job_id, state=stats.state, translated=stats.translated,
                                failed=stats.failed[:20]))
            if stats.state in {'paused', 'stopped'}:
                break  # лимит/обрыв или остановка: остальные моды не запрашиваются
        return results


class BatchTranslateDialog(QDialog):
    """Одно окно на все выбранные моды: предпросмотр объёма, запуск, остановка, проверка."""

    def __init__(self, chosen, parent=None):
        super().__init__(parent)
        from ck3loc.desktop.translate_dialog import TranslateOptions
        self.chosen = chosen
        self.worker = None
        self.results = []
        self.setWindowTitle(tr('Массовый перевод'))
        self.setSizeGripEnabled(True)
        self.resize(900, 640)
        v = QVBoxLayout(self)
        rows = sum(len(k) for _c, k in chosen)
        v.addWidget(QLabel(tr_format('Модов: {mods}; выбранных строк: {n}. Результаты сохраняются в черновики '
                                     'каждого мода и ничего не меняют до применения.', mods=len(chosen), n=rows)))
        self.opts = TranslateOptions()
        v.addWidget(self.opts)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.hide()
        v.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlainText('\n'.join(f'{c.name}: {len(k)}' for c, k in chosen))
        v.addWidget(self.log, 1)
        buttons = QHBoxLayout()
        self.start_button = QPushButton(tr('Запустить'))
        self.start_button.setProperty('accent', 'true')
        self.start_button.clicked.connect(self.start)
        buttons.addWidget(self.start_button)
        self.stop_button = QPushButton(tr('Остановить'))
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.stop_button)
        self.review_button = QPushButton(tr('Проверить и применить…'))
        self.review_button.clicked.connect(self.review)
        self.review_button.setEnabled(False)
        buttons.addWidget(self.review_button)
        buttons.addStretch(1)
        close = QPushButton(tr('Закрыть'))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        v.addLayout(buttons)
        self.opts.changed.connect(self.update_summary)
        self.update_summary()

    def update_summary(self, *_):
        size = self.opts.batch_size()
        upper = sum((len(k) + size - 1) // size for _c, k in self.chosen)
        self.summary.setText(tr_format('Не более {requests} запросов по {size} строк (ваниль CK3 и память переводов '
                                       'могут сократить число). Стоимость неизвестна; использованный лимит или оплата '
                                       'отправленных запросов не возвращается.', requests=upper, size=size))

    def start(self):
        from ck3loc.desktop.translate_dialog import check_key
        name = self.opts.provider()
        if not check_key(self, name):
            return
        settings.set_value('provider', name)
        self.opts.set_enabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.review_button.setEnabled(False)
        self.progress.show()
        self.log.appendPlainText(tr('Запущено. Остановка сохраняет готовые ответы.'))
        self.worker = BatchTranslateWorker(self.chosen, name, self.opts.options(), self)
        self.worker.progress.connect(lambda d, t, mod: (self.progress.setMaximum(max(t, 1)), self.progress.setValue(d),
                                                         self.progress.setFormat(f'{mod} · %p%')))
        self.worker.succeeded.connect(self._done)
        self.worker.failed.connect(lambda error: (self.log.appendPlainText(tr_format('Ошибка: {error}', error=error)),
                                                  self._done([])))
        self.worker.start()

    def stop(self):
        if self.worker is not None:
            self.worker.cancel()
            self.stop_button.setEnabled(False)
            self.log.appendPlainText(tr('Ожидаю завершения текущего запроса. Завершённые черновики сохранены.'))

    def _done(self, results):
        self.results = [r for r in results if r.get('job_id')]
        for r in results:
            if r.get('error'):
                self.log.appendPlainText(f"{r['name']}: {r['error']}")
                continue
            self.log.appendPlainText(tr_format('{mod}: {state}, готово строк {n}', mod=r['name'],
                                               state=tr(r['state']), n=r['translated']))
            for key, reason in r['failed']:
                self.log.appendPlainText(f'  {key}: {tr(reason)}')
        self.opts.set_enabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.review_button.setEnabled(bool(self.results))

    def review(self):
        from ck3loc.desktop.tasks import run_with_progress
        results = list(self.results)

        def work(conn, report, token):
            from ck3loc.core.jobs import preview_job
            from ck3loc.core.ops import load_project_context
            staged = []
            for i, r in enumerate(results, 1):
                report(i, len(results), r['name'])
                ctx = load_project_context(conn, r['mod_id'], r['source_lang'], r['target_lang'], mod_dir=r['mod_dir'])
                if ctx is not None:
                    staged.append({**r, 'preview': preview_job(ctx, r['job_id'])})
            return staged

        staged, error = run_with_progress(self, tr('Готовлю предпросмотр…'), work)
        if error:
            self.log.appendPlainText(tr_format('Ошибка: {error}', error=error))
            return
        applied = review_and_apply(self, staged)
        if applied is None:
            self.log.appendPlainText(tr('Применение отменено. Неприменённые черновики сохранены в «Истории действий» каждого мода.'))
            return
        for r in staged:
            self.log.appendPlainText(tr_format('{mod}: применено {n}', mod=r['name'], n=applied.get(r['job_id'], 0)))

    def done(self, result):
        if self.worker is not None and self.worker.isRunning():
            if QMessageBox.question(self, tr('Задание выполняется'),
                                    tr('Остановить перевод и сохранить готовые ответы в черновиках?')) \
                    != QMessageBox.StandardButton.Yes:
                return
            # Не блокируем окно ожиданием: закроемся, когда завершится текущий запрос.
            self.stop()
            self.worker.finished.connect(lambda: QDialog.done(self, result))
            return
        super().done(result)
