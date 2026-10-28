"""Review/resume saved drafts and undo actions without overwriting later edits."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QMessageBox
from ck3loc.core.i18n import tr, tr_format
from ck3loc.core.jobs import preview_undo, undo_action, discard_job
from ck3loc.desktop.review_dialog import ReviewDialog


class HistoryDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(tr('История действий'))
        self.resize(820, 500)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        v.addWidget(self.list)
        row = QHBoxLayout()
        for text, callback in [('Проверить / продолжить', self.open_job),
                               ('Отменить применение', self.undo), ('Отменить задание', self.discard)]:
            button = QPushButton(tr(text))
            button.clicked.connect(callback)
            row.addWidget(button)
        v.addLayout(row)
        close = QPushButton(tr('Закрыть'))
        close.clicked.connect(self.accept)
        v.addWidget(close)
        self.refresh()

    def refresh(self):
        self.entries = []
        self.list.clear()
        conn = self.ctx.conn
        for job in conn.execute('SELECT * FROM translation_jobs WHERE project_id=? ORDER BY created_at DESC,rowid DESC',
                                (self.ctx.project_id,)):
            total, done, applied = conn.execute(
                'SELECT COUNT(*), SUM(target_text IS NOT NULL), SUM(applied) FROM job_results WHERE job_id=?',
                (job['id'],)).fetchone()
            self.entries.append(('job', dict(job)))
            self.list.addItem(tr_format(
                '{date} · задание · {state} · {provider} · готово {done} из {total}, применено {applied}',
                date=job['created_at'], state=tr(job['state']), provider=job['provider'] or '—',
                done=done or 0, total=total or 0, applied=applied or 0))
        for action in conn.execute('SELECT * FROM translation_actions WHERE project_id=? AND undone=0 ORDER BY rowid DESC',
                                   (self.ctx.project_id,)):
            rows = conn.execute('SELECT COUNT(*) FROM action_rows WHERE action_id=? AND undone=0',
                                (action['id'],)).fetchone()[0]
            self.entries.append(('action', dict(action)))
            self.list.addItem(tr_format('{date} · {kind} · строк {n}', date=action['created_at'],
                                        kind=tr(action['kind']), n=rows))

    def selected(self, kind):
        i = self.list.currentRow()
        return self.entries[i][1] if 0 <= i < len(self.entries) and self.entries[i][0] == kind else None

    def open_job(self):
        job = self.selected('job')
        if job and job['state'] != 'discarded':
            from ck3loc.desktop.translate_dialog import TranslateDialog
            dialog = TranslateDialog(self.ctx.project['mod_id'], parent=self, ctx=self.ctx, job_id=job['id'])
            index = dialog.opts.combo.findData(job["provider"])
            if index >= 0:
                dialog.opts.combo.setCurrentIndex(index)
            dialog.exec()
            self.refresh()

    def undo(self):
        action = self.selected('action')
        if action:
            dialog = ReviewDialog(preview_undo(self.ctx.conn, action['id']), 'Отменить применение', default_changes=('restore',), parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                result = undo_action(self.ctx.conn, action['id'], dialog.selected_keys())
                QMessageBox.information(self, tr('Отменить применение'), tr_format(
                    'Возвращено строк: {n}; пропущено из-за поздних правок: {conflicts}. '
                    'Чтобы обновить файлы в игре, нажмите «Записать перевод в игру».',
                    n=len(result.changed), conflicts=len(result.conflicts)))
                self.refresh()

    def discard(self):
        job = self.selected('job')
        if job and QMessageBox.question(self, tr('Отменить задание'), tr('Удалить неприменённые черновики? Использованный лимит или оплата не возвращается.')) == QMessageBox.StandardButton.Yes:
            discard_job(self.ctx.conn, job['id'])
            self.refresh()
