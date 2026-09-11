"""Главное окно: боковая навигация, экраны, статус-строка, уведомления."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import settings
from ck3loc.desktop.glossary_page import GlossaryPage
from ck3loc.desktop.library_page import LibraryPage
from ck3loc.desktop.mod_page import ModPage
from ck3loc.desktop.settings_page import SettingsPage
from ck3loc.desktop.theme import make_app_icon, palette, stylesheet
from ck3loc.desktop.workers import ScanWorker

APP_TITLE = "CK3 Localization Manager"
NAV = [
    ("Библиотека", "library"),
    ("Глоссарий", "glossary"),
    ("Настройки", "settings"),
]


class NotificationsDialog(QDialog):
    def __init__(self, entries: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Уведомления")
        self.resize(720, 420)
        v = QVBoxLayout(self)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(entries) if entries
                          else "Пока нет уведомлений.")
        v.addWidget(text)
        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.accept)
        v.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = settings.load()
        self.theme = self.cfg.get("theme", "dark")
        self.notifications: list[str] = []
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 780)
        self.setMinimumSize(1000, 640)

        self.setWindowIcon(make_app_icon(self.theme))

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(22, 18, 22, 12)
        rv.setSpacing(16)

        self.page_title = QLabel("Библиотека модов")
        self.page_title.setProperty("role", "h1")
        rv.addWidget(self.page_title)

        self.stack = QStackedWidget()
        self.library = LibraryPage(self.theme)
        self.library.open_mod.connect(self.open_mod)
        self.library.rescan.connect(self.start_scan)
        self.library.batch.connect(self.open_batch)
        self.mod_page = ModPage(self.theme)
        self.mod_page.back.connect(self.show_library)
        self.mod_page.note.connect(self.add_note)
        self.mod_page.request_translate.connect(self.open_translate)
        self.glossary = GlossaryPage(self.theme)
        self.settings_page = SettingsPage(self.theme)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self.settings_page.langs_changed.connect(self._langs_changed)
        self.settings_page.ui_language_changed.connect(self.change_ui_language)
        for w in (self.library, self.mod_page, self.glossary, self.settings_page):
            self.stack.addWidget(w)
        # на карточке мода общий заголовок скрыт: название показывает сама
        # страница, иначе оно дублируется
        self.stack.currentChanged.connect(
            lambda i: self.page_title.setVisible(i != 1)
        )
        rv.addWidget(self.stack, stretch=1)
        root.addWidget(right, stretch=1)
        self.setCentralWidget(central)

        # статус-строка
        status = self.statusBar()
        self.status_label = QLabel("Готово")
        status.addWidget(self.status_label, stretch=1)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.hide()
        status.addPermanentWidget(self.progress)
        self.btn_notes = QPushButton("Уведомления")
        self.btn_notes.setFlat(True)
        self.btn_notes.clicked.connect(self.show_notifications)
        status.addPermanentWidget(self.btn_notes)

        self._build_shortcuts()
        self.apply_theme(self.theme)
        self.retranslate()
        self.worker: ScanWorker | None = None
        if self.cfg.get("scan_on_start", True):
            QTimer.singleShot(300, self.start_scan)

    def _build_shortcuts(self):
        QShortcut(QKeySequence("F5"), self, activated=self.start_scan)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape)
        QShortcut(QKeySequence("Ctrl+1"), self,
                  activated=lambda: self.go("library"))
        QShortcut(QKeySequence("Ctrl+2"), self,
                  activated=lambda: self.go("glossary"))
        QShortcut(QKeySequence("Ctrl+3"), self,
                  activated=lambda: self.go("settings"))

    def _focus_search(self):
        if self.stack.currentIndex() == 0:
            self.library.focus_search()
        elif self.stack.currentIndex() == 1:
            self.mod_page.row_search.setFocus()
            self.mod_page.row_search.selectAll()

    def _escape(self):
        if self.stack.currentIndex() == 1:
            self.show_library()

    # ---------- каркас ----------

    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(210)
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 18, 0, 14)
        v.setSpacing(2)

        logo = QLabel("CK3 Localization")
        logo.setObjectName("Logo")
        v.addWidget(logo)
        sub = QLabel("менеджер переводов модов")
        sub.setObjectName("LogoSub")
        v.addWidget(sub)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (title, key) in enumerate(NAV):
            btn = QPushButton(title)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav_group.addButton(btn, i)
            v.addWidget(btn)
        v.addStretch(1)

        self.hint = QLabel(
            "Файлы автора мода не изменяются — приложение только добавляет "
            "перевод, и всё записанное можно восстановить из базы."
        )
        self.hint.setObjectName("SidebarNote")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)
        return bar

    def go(self, key: str):
        index = {"library": 0, "glossary": 2, "settings": 3}[key]
        titles = {
            "library": "Библиотека модов",
            "glossary": "Глоссарий терминов",
            "settings": "Настройки",
        }
        self.stack.setCurrentIndex(index)
        from ck3loc.core.i18n import tr

        self.page_title.setText(tr(titles[key]))
        self.page_title.setVisible(True)
        if key == "glossary":
            self.glossary.refresh()
        for i, (_t, k) in enumerate(NAV):
            self.nav_group.button(i).setChecked(k == key)

    def show_library(self):
        self.go("library")

    def apply_theme(self, name: str):
        self.theme = name
        settings.set_value("theme", name)
        self.setStyleSheet(stylesheet(name))
        self.setWindowIcon(make_app_icon(name))
        self.library.apply_theme(name)
        self.mod_page.theme = name
        if self.mod_page.ctx is not None:
            self.mod_page.refresh()

    # ---------- действия ----------

    def start_scan(self):
        if self.worker is not None and self.worker.isRunning():
            return
        cfg = settings.load()
        self.library.set_busy(True)
        self.progress.show()
        self.status_label.setText("Сканирование библиотеки…")
        self.worker = ScanWorker(cfg["source_lang"], cfg["target_lang"],
                                 cfg.get("steam_path", ""))
        self.worker.progress.connect(self._on_progress)
        self.worker.note.connect(self.add_note)
        self.worker.finished_rows.connect(self._on_scan_done)
        self.worker.start()

    def _on_progress(self, i: int, total: int, name: str):
        self.progress.setMaximum(total)
        self.progress.setValue(i)
        self.status_label.setText(f"Сканирование: {i} из {total} — {name}")

    def _on_scan_done(self, rows: list):
        self.library.set_rows(rows)
        self.library.set_busy(False)
        self.progress.hide()
        if not rows:
            self.status_label.setText(
                "Моды не найдены. Проверьте путь к Steam в Настройках."
            )
            return
        with_loc = [r for r in rows if r.has_loc]
        none = sum(1 for r in with_loc if r.coverage == 0.0)
        self.status_label.setText(
            f"Готово: {len(rows)} модов, {len(with_loc)} с локализацией, "
            f"{none} без перевода"
        )
        self.add_note(f"Сканирование завершено: {len(rows)} модов.")

    def open_mod(self, mod_id: str):
        if self.mod_page.load(mod_id):
            self.stack.setCurrentIndex(1)
            # заголовок мода показывает сама страница — общий скрываем,
            # чтобы название не дублировалось
            self.page_title.setVisible(False)
            for i in range(len(NAV)):
                self.nav_group.button(i).setChecked(False)

    def open_translate(self, mod_id: str):
        from ck3loc.core.ops import rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, estimate
        from ck3loc.desktop.translate_dialog import TranslateDialog

        ctx = self.mod_page.ctx
        if ctx is None:
            return
        rows = rows_to_translate(ctx, "all")
        if not rows:
            QMessageBox.information(self, "Перевод",
                                    "Переводить нечего — всё актуально.")
            return
        self.status_label.setText("Считаю смету…")
        vl = build_vanilla_lookup(ctx.project["source_lang"],
                                  ctx.project["target_lang"])
        est = estimate(ctx, rows, vanilla_lookup=vl)
        api_rows = est.rows - est.covered_by_vanilla - est.covered_by_memory
        c = palette(self.theme)
        html = (
            f"Строк на перевод: <b>{est.rows}</b><br>"
            f"<span style='color:{c['ok']}'>Закроется ванилью CK3 бесплатно: "
            f"{est.covered_by_vanilla}</span><br>"
            f"<span style='color:{c['ok']}'>Закроется памятью переводов: "
            f"{est.covered_by_memory}</span><br>"
            f"Уйдёт в API: <b>{api_rows}</b> строк, ~{est.chars_to_api} символов"
        )
        self.status_label.setText("Готово")
        dlg = TranslateDialog(mod_id, html, parent=self)
        dlg.exec()
        if dlg.stats is not None:
            self.add_note(
                f"«{ctx.scan.name}»: переведено {dlg.stats.translated} строк "
                f"(ошибок {len(dlg.stats.failed)})"
            )
        self.mod_page.reload()

    def open_batch(self):
        from ck3loc.desktop.translate_dialog import BatchDialog

        dlg = BatchDialog(parent=self)
        dlg.exec()
        self.add_note("Пакетный перевод: сессия закрыта.")

    def _langs_changed(self):
        self.add_note("Языки изменены — пересканируйте библиотеку.")

    def retranslate(self):
        """Применить язык интерфейса ко всему окну."""
        from ck3loc.desktop.translate_ui import translate_tree

        translate_tree(self)
        self.library.refresh_table()

    def change_ui_language(self, code: str):
        from ck3loc.core.i18n import set_language

        set_language(code)
        settings.set_value("ui_lang", code)
        self.retranslate()
        self.add_note("Язык программы изменён.")

    # ---------- уведомления ----------

    def add_note(self, text: str):
        import time

        entry = f"[{time.strftime('%H:%M')}] {text}"
        self.notifications.append(entry)
        self.btn_notes.setText(f"Уведомления ({len(self.notifications)})")
        self.btn_notes.setStyleSheet(
            f"color: {palette(self.theme)['accent']}; font-weight: 600;"
        )
        self.status_label.setText(text)

    def show_notifications(self):
        NotificationsDialog(list(reversed(self.notifications)), self).exec()
        self.btn_notes.setStyleSheet("")

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.mod_page.close_db()
        self.glossary.close_db()
        super().closeEvent(event)
