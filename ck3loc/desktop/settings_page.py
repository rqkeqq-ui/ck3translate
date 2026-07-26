"""Экран «Настройки»: языки, режим записи, ключи API, пути, тема."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import settings
from ck3loc.core.db import backups_dir, data_dir
from ck3loc.core.vanilla import find_ck3_game_dir, game_languages
from ck3loc.desktop.widgets import Card, field_row
from ck3loc.providers.registry import PROVIDERS, get_api_key, set_api_key


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    langs_changed = Signal()

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        cfg = settings.load()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # --- языки и режимы ---
        card = Card("Языки и запись перевода")
        langs = game_languages()
        self.source = QComboBox()
        self.source.addItems(langs)
        self.source.setCurrentText(cfg["source_lang"])
        self.source.currentTextChanged.connect(
            lambda t: (settings.set_value("source_lang", t),
                       self.langs_changed.emit())
        )
        card.add(field_row(
            "Исходный язык", self.source,
            "Если в моде его нет или он неполный, приложение само предложит "
            "самый полный язык мода."))

        self.target = QComboBox()
        self.target.addItems(langs)
        self.target.setCurrentText(cfg["target_lang"])
        self.target.currentTextChanged.connect(
            lambda t: (settings.set_value("target_lang", t),
                       self.langs_changed.emit())
        )
        card.add(field_row("Целевой язык", self.target))

        self.write_mode = QComboBox()
        self.write_mode.addItem("Внутрь мода (рекомендуется)", "in_mod")
        self.write_mode.addItem("Отдельный патч-мод", "patch_mod")
        self.write_mode.setCurrentIndex(0 if cfg["write_mode"] == "in_mod" else 1)
        self.write_mode.currentIndexChanged.connect(
            lambda: settings.set_value("write_mode",
                                       self.write_mode.currentData())
        )
        card.add(field_row(
            "Куда писать по умолчанию", self.write_mode,
            "«Внутрь мода» — перевод работает сразу; если Steam сотрёт его при "
            "обновлении, приложение восстановит из базы. Патч-мод переживает "
            "обновления, но требует места в плейсете."))
        v.addWidget(card)

        # --- провайдеры ---
        keys_card = Card("Ключи API переводчиков")
        note = QLabel(
            "Ключи хранятся в защищённом хранилище Windows (Credential Manager), "
            "не в файлах приложения. Перевод через файл-задание для нейросети "
            "работает без ключей."
        )
        note.setProperty("role", "dim")
        note.setWordWrap(True)
        keys_card.add(note)

        self.key_edits: dict[str, QLineEdit] = {}
        self.key_states: dict[str, QLabel] = {}
        for name, cls in PROVIDERS.items():
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setPlaceholderText("вставьте ключ…")
            self.key_edits[name] = edit
            hl.addWidget(edit, stretch=1)
            state = QLabel()
            state.setMinimumWidth(110)
            self.key_states[name] = state
            hl.addWidget(state)
            btn = QPushButton("Сохранить")
            btn.clicked.connect(lambda _=False, n=name: self._save_key(n))
            hl.addWidget(btn)
            btn_del = QPushButton("Удалить")
            btn_del.clicked.connect(lambda _=False, n=name: self._clear_key(n))
            hl.addWidget(btn_del)
            keys_card.add(field_row(cls.info.title, row))
        v.addWidget(keys_card)

        # --- дополнительные параметры провайдеров ---
        extra = Card("Дополнительно для LLM и Яндекса")
        self.claude_model = QLineEdit(cfg.get("claude_model", ""))
        self.claude_model.setPlaceholderText("claude-sonnet-5 (по умолчанию)")
        self.claude_model.editingFinished.connect(
            lambda: settings.set_value("claude_model", self.claude_model.text().strip())
        )
        extra.add(field_row("Модель Claude", self.claude_model))
        self.openai_url = QLineEdit(cfg.get("openai_base_url", ""))
        self.openai_url.setPlaceholderText("https://api.openai.com/v1")
        self.openai_url.editingFinished.connect(
            lambda: settings.set_value("openai_base_url",
                                       self.openai_url.text().strip())
        )
        extra.add(field_row("Адрес OpenAI-совместимого API", self.openai_url))
        self.openai_model = QLineEdit(cfg.get("openai_model", ""))
        self.openai_model.setPlaceholderText("gpt-4o-mini")
        self.openai_model.editingFinished.connect(
            lambda: settings.set_value("openai_model",
                                       self.openai_model.text().strip())
        )
        extra.add(field_row("Модель OpenAI-совместимого API", self.openai_model))
        self.yandex_folder = QLineEdit(cfg.get("yandex_folder_id", ""))
        self.yandex_folder.setPlaceholderText("folder id из Яндекс Облака")
        self.yandex_folder.editingFinished.connect(
            lambda: settings.set_value("yandex_folder_id",
                                       self.yandex_folder.text().strip())
        )
        extra.add(field_row("Yandex folder ID", self.yandex_folder))
        v.addWidget(extra)

        # --- пути и данные ---
        paths = Card("Пути и данные")
        steam_row = QWidget()
        sl = QHBoxLayout(steam_row)
        sl.setContentsMargins(0, 0, 0, 0)
        self.steam_path = QLineEdit(cfg.get("steam_path", ""))
        self.steam_path.setPlaceholderText("определяется автоматически")
        self.steam_path.editingFinished.connect(
            lambda: settings.set_value("steam_path", self.steam_path.text().strip())
        )
        sl.addWidget(self.steam_path, stretch=1)
        btn_browse = QPushButton("Выбрать…")
        btn_browse.clicked.connect(self._pick_steam)
        sl.addWidget(btn_browse)
        paths.add(field_row("Папка Steam", steam_row))

        game = find_ck3_game_dir()
        game_label = QLabel(str(game) if game else "игра не найдена")
        game_label.setProperty("role", "dim")
        game_label.setWordWrap(True)
        paths.add(field_row("Установленная CK3", game_label,
                            "Используется для официальных переводов ванильных строк."))

        data_row = QWidget()
        dl = QHBoxLayout(data_row)
        dl.setContentsMargins(0, 0, 0, 0)
        data_label = QLabel(str(data_dir()))
        data_label.setProperty("role", "dim")
        data_label.setWordWrap(True)
        dl.addWidget(data_label, stretch=1)
        btn_open = QPushButton("Открыть папку")
        btn_open.clicked.connect(lambda: self._open_folder(data_dir()))
        dl.addWidget(btn_open)
        btn_backup = QPushButton("Открыть резервные копии")
        btn_backup.clicked.connect(lambda: self._open_folder(backups_dir()))
        dl.addWidget(btn_backup)
        paths.add(field_row("База приложения", data_row,
                            "Здесь хранятся все переводы, история и снимки. "
                            "Скопируйте эту папку, чтобы сохранить всю работу."))
        v.addWidget(paths)

        # --- интерфейс ---
        ui = Card("Интерфейс")
        self.theme_box = QComboBox()
        self.theme_box.addItem("Тёмная", "dark")
        self.theme_box.addItem("Светлая", "light")
        self.theme_box.setCurrentIndex(0 if cfg.get("theme") == "dark" else 1)
        self.theme_box.currentIndexChanged.connect(
            lambda: self.theme_changed.emit(self.theme_box.currentData())
        )
        ui.add(field_row("Оформление", self.theme_box))
        self.scan_start = QCheckBox("Сканировать библиотеку при запуске")
        self.scan_start.setChecked(bool(cfg.get("scan_on_start", True)))
        self.scan_start.toggled.connect(
            lambda val: settings.set_value("scan_on_start", val)
        )
        ui.add(self.scan_start)
        v.addWidget(ui)
        v.addStretch(1)

        self._refresh_keys()

    # ---------- обработчики ----------

    def _refresh_keys(self):
        for name, label in self.key_states.items():
            label.setText("ключ сохранён" if get_api_key(name) else "ключа нет")
            label.setProperty("role", "dim")
            label.style().unpolish(label)
            label.style().polish(label)

    def _save_key(self, name: str):
        key = self.key_edits[name].text().strip()
        if not key:
            QMessageBox.information(self, "Ключи API", "Введите ключ.")
            return
        try:
            set_api_key(name, key)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Ключи API",
                                f"Не удалось сохранить ключ: {e}")
            return
        self.key_edits[name].clear()
        self._refresh_keys()

    def _clear_key(self, name: str):
        set_api_key(name, "")
        self._refresh_keys()

    def _pick_steam(self):
        path = QFileDialog.getExistingDirectory(self, "Папка Steam")
        if path:
            self.steam_path.setText(path)
            settings.set_value("steam_path", path)

    def _open_folder(self, path: Path):
        try:
            os.startfile(str(path))  # noqa: S606 — открытие проводника Windows
        except Exception:  # noqa: BLE001
            subprocess.Popen(["explorer", str(path)])
