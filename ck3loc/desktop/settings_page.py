"""Экран «Настройки»: языки, режим записи, ключи API, пути, тема."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import settings
from ck3loc.core.community_db import (
    configured_repository_url,
    discover_community_database,
    workshop_page_url,
)
from ck3loc.core.db import backups_dir, data_dir
from ck3loc.core.i18n import DEFAULT_UI_LANG, available_languages
from ck3loc.core.vanilla import find_ck3_game_dir, game_languages
from ck3loc.desktop.widgets import Card, field_row
from ck3loc.providers.registry import PROVIDERS, get_api_key, set_api_key


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    langs_changed = Signal()
    ui_language_changed = Signal(str)

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

        # --- моды-русификаторы ---
        prov = Card("Моды-русификаторы")
        note_prov = QLabel(
            "Приложение находит отдельные моды, которые переводят другие моды, "
            "и не предлагает переводить то, что уже переведено ими. "
            "Определяется по пересечению ключей и зависимостям мода."
        )
        note_prov.setProperty("role", "dim")
        note_prov.setWordWrap(True)
        prov.add(note_prov)

        self.provider_detect = QCheckBox("Учитывать моды-русификаторы")
        self.provider_detect.setChecked(bool(cfg.get("provider_detect", True)))
        self.provider_detect.toggled.connect(
            lambda val: settings.set_value("provider_detect", val)
        )
        prov.add(self.provider_detect)

        self.min_ratio = QDoubleSpinBox()
        self.min_ratio.setRange(0.05, 1.0)
        self.min_ratio.setSingleStep(0.05)
        self.min_ratio.setDecimals(2)
        self.min_ratio.setValue(float(cfg.get("provider_min_ratio", 0.25)))
        self.min_ratio.valueChanged.connect(
            lambda val: settings.set_value("provider_min_ratio", float(val))
        )
        prov.add(field_row(
            "Порог: доля ключей", self.min_ratio,
            "Какую часть строк мода должен покрывать русификатор, чтобы "
            "считаться его переводом. По умолчанию 0,25 — на реальных модах "
            "настоящий русификатор даёт 0,9 и выше."))

        self.min_keys = QSpinBox()
        self.min_keys.setRange(5, 5000)
        self.min_keys.setValue(int(cfg.get("provider_min_keys", 30)))
        self.min_keys.valueChanged.connect(
            lambda val: settings.set_value("provider_min_keys", int(val))
        )
        prov.add(field_row(
            "Порог: минимум строк", self.min_keys,
            "Ниже этого числа совпадений связь считается случайной."))
        v.addWidget(prov)

        # --- подписная база сообщества ---
        community_card = Card("CK3Loc Community Database")
        community_note = QLabel(
            "Необязательная подписка Steam Workshop доставляет глоссарии, "
            "проверенные связи оригинальных модов с русификаторами и правила "
            "обработки отдельных модов. Включать её в плейсет не нужно."
        )
        community_note.setProperty("role", "dim")
        community_note.setWordWrap(True)
        community_card.add(community_note)
        self.community_enabled = QCheckBox("Использовать Community Database")
        self.community_enabled.setChecked(
            bool(cfg.get("community_db_enabled", True))
        )
        self.community_enabled.toggled.connect(self._community_toggled)
        community_card.add(self.community_enabled)
        community_row = QWidget()
        cr = QHBoxLayout(community_row)
        cr.setContentsMargins(0, 0, 0, 0)
        self.community_status = QLabel()
        self.community_status.setProperty("role", "dim")
        self.community_status.setWordWrap(True)
        cr.addWidget(self.community_status, stretch=1)
        self.community_open = QPushButton("Открыть в Workshop")
        self.community_open.clicked.connect(self._open_community_page)
        cr.addWidget(self.community_open)
        refresh_community = QPushButton("Проверить")
        refresh_community.clicked.connect(self._refresh_community_db)
        cr.addWidget(refresh_community)
        community_card.add(community_row)
        v.addWidget(community_card)

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
        self.ui_lang = QComboBox()
        for code, name in available_languages():
            self.ui_lang.addItem(name, code)
        idx = self.ui_lang.findData(cfg.get("ui_lang") or DEFAULT_UI_LANG)
        self.ui_lang.setCurrentIndex(max(0, idx))
        self.ui_lang.currentIndexChanged.connect(
            lambda: self.ui_language_changed.emit(self.ui_lang.currentData())
        )
        ui.add(field_row(
            "Язык программы", self.ui_lang,
            "Меняется сразу. Язык перевода модов задаётся выше отдельно."))

        self.theme_box = QComboBox()
        self.theme_box.addItem("Тёмная", "dark")
        self.theme_box.addItem("Светлая", "light")
        self.theme_box.setCurrentIndex(0 if cfg.get("theme") == "dark" else 1)
        self.theme_box.currentIndexChanged.connect(
            lambda: self.theme_changed.emit(self.theme_box.currentData())
        )
        ui.add(field_row("Оформление", self.theme_box))
        self.fetch_covers = QCheckBox("Загружать обложки модов из мастерской")
        self.fetch_covers.setChecked(bool(cfg.get("fetch_covers", True)))
        self.fetch_covers.toggled.connect(
            lambda val: settings.set_value("fetch_covers", val)
        )
        ui.add(self.fetch_covers)
        self.covers_in_list = QCheckBox("Показывать обложки в списке модов")
        self.covers_in_list.setToolTip(
            "Список станет нагляднее, но при первом запуске придётся "
            "скачать обложку каждого мода"
        )
        self.covers_in_list.setChecked(bool(cfg.get("show_covers_in_list")))
        self.covers_in_list.toggled.connect(
            lambda val: settings.set_value("show_covers_in_list", val)
        )
        ui.add(self.covers_in_list)
        self.scan_start = QCheckBox("Сканировать библиотеку при запуске")
        self.scan_start.setChecked(bool(cfg.get("scan_on_start", True)))
        self.scan_start.toggled.connect(
            lambda val: settings.set_value("scan_on_start", val)
        )
        ui.add(self.scan_start)
        v.addWidget(ui)
        v.addStretch(1)

        self._refresh_keys()
        self._refresh_community_db()

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

    def _community_toggled(self, enabled: bool):
        settings.set_value("community_db_enabled", enabled)
        self._refresh_community_db()

    def _refresh_community_db(self):
        result = discover_community_database(
            enabled=self.community_enabled.isChecked()
        )
        database = result.database
        if result.state == "ready" and database is not None:
            self.community_status.setText(
                f"Подключена версия {database.database_version} · "
                f"терминов {len(database.glossaries)} · "
                f"связей {len(database.translations)}"
            )
        elif result.state == "incompatible" and database is not None:
            self.community_status.setText(
                "Нужно обновить приложение до версии "
                f"{database.minimum_app_version} или новее."
            )
        elif result.state == "invalid":
            detail = result.errors[0] if result.errors else "ошибка формата"
            self.community_status.setText(f"База повреждена: {detail}")
        elif result.state == "downloading":
            self.community_status.setText("Подписка найдена, Steam ещё загружает файлы.")
        elif result.state == "disabled":
            self.community_status.setText("Отключена в настройках.")
        elif result.workshop_id:
            self.community_status.setText("Не установлена или нет подписки.")
        else:
            self.community_status.setText(
                "База готовится к публикации. Приложение уже можно использовать без подписки."
            )
        item_id = database.workshop_id if database else result.workshop_id
        workshop_url = workshop_page_url(item_id)
        self.community_open.setText("Открыть в Workshop" if workshop_url else "Новости на GitHub")
        self.community_open.setEnabled(bool(workshop_url or configured_repository_url()))

    def _open_community_page(self):
        result = discover_community_database(
            enabled=self.community_enabled.isChecked()
        )
        item_id = result.database.workshop_id if result.database else result.workshop_id
        url = workshop_page_url(item_id) or configured_repository_url()
        if url:
            webbrowser.open(url)

    def _pick_steam(self):
        path = QFileDialog.getExistingDirectory(self, "Папка Steam")
        if path:
            self.steam_path.setText(path)
            settings.set_value("steam_path", path)

    def _open_folder(self, path: Path):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
