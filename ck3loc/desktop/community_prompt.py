"""Optional Workshop reminder, based on locally installed database files."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ck3loc.core import settings
from ck3loc.core.community_db import DiscoveryResult, discover_community_database, workshop_page_url
from ck3loc.core.i18n import tr


def database_status() -> DiscoveryResult:
    config = settings.load()
    steam = config.get("steam_path", "")
    return discover_community_database(
        Path(steam) if steam else None,
        enabled=bool(config.get("community_db_enabled", True)),
    )


class CommunityPrompt(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CK3 Localization Manager — Community Database")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        heading = QLabel(tr("Добавьте Community Database"))
        heading.setProperty("role", "h1")
        layout.addWidget(heading)
        description = QLabel(tr(
            "Подпишитесь на базу в Steam Workshop, чтобы получать общие термины, "
            "связи модов с переводами и правила обработки по мере обновления базы. "
            "Приложением можно пользоваться без подписки."
        ))
        description.setWordWrap(True)
        layout.addWidget(description)
        warning = QLabel(tr("Не включайте базу в playset — она нужна только приложению."))
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.dont_show = QCheckBox(tr("Больше не показывать при запуске"))
        layout.addWidget(self.dont_show)
        buttons = QHBoxLayout()
        self.subscribe = QPushButton(tr("Открыть Steam Workshop"))
        self.subscribe.setProperty("accent", "true")
        self.subscribe.clicked.connect(self.open_workshop)
        buttons.addWidget(self.subscribe)
        self.check = QPushButton(tr("Проверить загрузку"))
        self.check.clicked.connect(self.refresh)
        buttons.addWidget(self.check)
        self.continue_button = QPushButton(tr("Продолжить без базы"))
        self.continue_button.clicked.connect(self.accept)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)
        self.finished.connect(self.remember_choice)
        self.refresh()

    def open_workshop(self) -> None:
        url = workshop_page_url()
        if url:
            webbrowser.open(url)

    def refresh(self) -> None:
        result = database_status()
        messages = {
            "ready": "База установлена и готова к использованию.",
            "missing": "Файлы базы не найдены. После подписки дождитесь загрузки Steam и нажмите «Проверить загрузку».",
            "downloading": "Steam ещё загружает базу. Повторите проверку после завершения загрузки.",
            "invalid": "Файлы базы повреждены. Обновите подписку в Steam или продолжите без базы.",
            "incompatible": "Для этой базы нужна более новая версия приложения. Обновите приложение или продолжите без базы.",
            "disabled": "Community Database отключена в настройках.",
        }
        self.status.setText(tr(messages.get(result.state, messages["missing"])))
        self.continue_button.setText(tr("Продолжить") if result.state == "ready" else tr("Продолжить без базы"))

    def remember_choice(self, _result: int) -> None:
        if self.dont_show.isChecked():
            settings.set_value("community_db_prompt_enabled", False)


def show_community_prompt(parent=None) -> None:
    if not settings.get("community_db_prompt_enabled") or not workshop_page_url():
        return
    if database_status().state in ("ready", "disabled"):
        return
    CommunityPrompt(parent).exec()
