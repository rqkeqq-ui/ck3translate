"""Окно первого запуска: язык интерфейса и целевой язык перевода.

Левая колонка — язык программы. Правая повторяет выбор левой, но её можно
задать отдельно: язык интерфейса при этом не меняется.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ck3loc.core.i18n import (
    UI_LANGUAGES,
    available_languages,
    ck3_language_for,
    set_language,
    system_language,
    tr,
)
from ck3loc.desktop.translate_ui import translate_tree
from ck3loc.desktop.widgets import Card

# названия языков локализации CK3 на их собственном языке
CK3_LANG_TITLES = {
    "english": "English",
    "french": "Français",
    "german": "Deutsch",
    "spanish": "Español",
    "russian": "Русский",
    "simp_chinese": "简体中文",
    "korean": "한국어",
    "polish": "Polski",
    "japanese": "日本語",
}


class FirstRunDialog(QDialog):
    def __init__(self, ck3_languages: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CK3 Localization Manager")
        self.resize(720, 520)
        self._target_touched = False

        v = QVBoxLayout(self)
        v.setSpacing(14)

        title = QLabel("Выберите языки")
        title.setProperty("role", "h1")
        v.addWidget(title)
        hint = QLabel(
            "Слева — язык программы, справа — язык, на который будете "
            "переводить моды. Целевой язык повторяет выбор слева, но его "
            "можно задать отдельно."
        )
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        v.addWidget(hint)

        columns = QHBoxLayout()
        columns.setSpacing(12)

        ui_card = Card("Язык программы")
        self.ui_list = QListWidget()
        for code, name in available_languages():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.ui_list.addItem(item)
        self.ui_list.currentItemChanged.connect(self._ui_changed)
        ui_card.add(self.ui_list, stretch=1)
        columns.addWidget(ui_card, stretch=1)

        target_card = Card("Язык перевода модов")
        self.target_list = QListWidget()
        langs = ck3_languages or list(CK3_LANG_TITLES)
        for lang in langs:
            item = QListWidgetItem(CK3_LANG_TITLES.get(lang, lang))
            item.setData(Qt.ItemDataRole.UserRole, lang)
            self.target_list.addItem(item)
        self.target_list.itemClicked.connect(self._target_clicked)
        target_card.add(self.target_list, stretch=1)
        columns.addWidget(target_card, stretch=1)
        v.addLayout(columns)

        self.note = QLabel()
        self.note.setProperty("role", "dim")
        self.note.setWordWrap(True)
        v.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_ok = QPushButton("Продолжить")
        self.btn_ok.setProperty("accent", "true")
        self.btn_ok.clicked.connect(self.accept)
        buttons.addWidget(self.btn_ok)
        v.addLayout(buttons)

        self._select_ui(system_language())

    # ---------- логика выбора ----------

    def _select_ui(self, code: str):
        for i in range(self.ui_list.count()):
            if self.ui_list.item(i).data(Qt.ItemDataRole.UserRole) == code:
                self.ui_list.setCurrentRow(i)
                return
        self.ui_list.setCurrentRow(0)

    def _select_target(self, lang: str):
        for i in range(self.target_list.count()):
            if self.target_list.item(i).data(Qt.ItemDataRole.UserRole) == lang:
                self.target_list.setCurrentRow(i)
                return

    def _ui_changed(self, current, _previous):
        if current is None:
            return
        code = current.data(Qt.ItemDataRole.UserRole)
        set_language(code)
        translate_tree(self)
        if not self._target_touched:
            self._select_target(ck3_language_for(code))
        self._update_note()

    def _target_clicked(self, _item):
        # выбор целевого языка не меняет язык программы
        self._target_touched = True
        self._update_note()

    def _update_note(self):
        target = self.target_language()
        self.note.setText(
            tr("Переводить моды будем на язык:") + " "
            + CK3_LANG_TITLES.get(target, target)
            + ("  " + tr("(можно изменить позже в настройках)"))
        )

    # ---------- результат ----------

    def ui_language(self) -> str:
        item = self.ui_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else "ru"

    def target_language(self) -> str:
        item = self.target_list.currentItem()
        if item is not None:
            return item.data(Qt.ItemDataRole.UserRole)
        return ck3_language_for(self.ui_language())

    def source_language_default(self) -> str:
        """Исходный язык по умолчанию — английский, кроме случая, когда
        целевой сам английский."""
        return "russian" if self.target_language() == "english" else "english"
