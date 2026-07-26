"""Мелкие переиспользуемые элементы интерфейса."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ck3loc.desktop.theme import palette

# статус строки → (подпись, цвет из палитры)
STATUS_UI = {
    "missing": ("Не переведено", "err"),
    "machine": ("Машинный", "info"),
    "reviewed": ("Проверено", "ok"),
    "approved": ("Утверждено", "ok"),
    "stale": ("Устарело", "warn"),
    "conflict": ("Конфликт", "err"),
    "orphan": ("Осиротело", "text_dim"),
    "extra": ("Только в цели", "text_dim"),
    "native": ("Родной перевод", "text_dim"),
    "edited_outside": ("Правлено извне", "warn"),
}


def status_label(status: str) -> str:
    return STATUS_UI.get(status, (status, "text_dim"))[0]


def status_color(status: str, theme: str = "dark") -> str:
    key = STATUS_UI.get(status, (status, "text_dim"))[1]
    return palette(theme)[key]


class Tile(QFrame):
    """Кликабельная плитка со значением и подписью."""

    clicked = Signal()

    def __init__(self, caption: str, value: str = "—", accent: str = "text",
                 theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._accent = accent
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(2)
        self.value_label = QLabel(value)
        v.addWidget(self.value_label)
        cap = QLabel(caption)
        cap.setProperty("role", "dim")
        cap.setWordWrap(True)
        v.addWidget(cap)
        self.apply_theme(theme)

    def apply_theme(self, theme: str):
        """Цвет значения задаётся инлайном, поэтому его нужно обновлять
        при смене оформления."""
        self.value_label.setStyleSheet(
            "font-size: 24px; font-weight: 600; background: transparent; "
            f"color: {palette(theme)[self._accent]};"
        )

    def set_value(self, value):
        self.value_label.setText(str(value))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Card(QFrame):
    """Панель-карточка с заголовком."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(10)
        if title:
            lab = QLabel(title)
            lab.setProperty("role", "h2")
            self.body.addWidget(lab)

    def add(self, widget: QWidget, stretch: int = 0):
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout):
        self.body.addLayout(layout)


def align_headers(table, left_columns=(), right_columns=()) -> None:
    """Выровнять заголовки так же, как данные в столбцах."""
    for col in left_columns:
        item = table.horizontalHeaderItem(col)
        if item:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
    for col in right_columns:
        item = table.horizontalHeaderItem(col)
        if item:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )


def field_row(caption: str, widget: QWidget, hint: str = "") -> QWidget:
    """Строка «подпись — поле — пояснение» для экранов настроек."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    row = QHBoxLayout()
    lab = QLabel(caption)
    lab.setMinimumWidth(190)
    row.addWidget(lab)
    row.addWidget(widget, stretch=1)
    v.addLayout(row)
    if hint:
        h = QLabel(hint)
        h.setProperty("role", "dim")
        h.setWordWrap(True)
        h.setContentsMargins(196, 0, 0, 0)
        v.addWidget(h)
    return w
