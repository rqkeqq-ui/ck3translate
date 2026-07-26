"""Переиспользуемые элементы интерфейса."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ck3loc.desktop.theme import MONO, palette

# статус строки → (подпись, ключ цвета)
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
    return palette(theme)[STATUS_UI.get(status, (status, "text_dim"))[1]]


class Tile(QFrame):
    """Плитка сводки: значение, подпись и необязательная вторая строка.

    Кликом фильтрует список; активная плитка подсвечивается рамкой.
    """

    clicked = Signal()

    def __init__(self, caption: str, accent: str = "text", theme: str = "dark",
                 tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(84)
        self.setMinimumWidth(112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if tooltip:
            self.setToolTip(tooltip)
        self._accent = accent

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(1)
        self.value_label = QLabel("0")
        v.addWidget(self.value_label)
        self.caption_label = QLabel(caption)
        self.caption_label.setProperty("role", "dim")
        v.addWidget(self.caption_label)
        self.sub_label = QLabel("")
        self.sub_label.setProperty("role", "dim")
        self.sub_label.setStyleSheet("font-size: 11px;")
        self.sub_label.hide()
        v.addWidget(self.sub_label)
        v.addStretch(1)
        self.apply_theme(theme)

    def apply_theme(self, theme: str):
        self.value_label.setStyleSheet(
            "font-size: 25px; font-weight: 600; background: transparent; "
            f"color: {palette(theme)[self._accent]};"
        )

    def set_value(self, value, sub: str = ""):
        self.value_label.setText(str(value))
        if sub:
            self.sub_label.setText(sub)
            self.sub_label.show()
        else:
            self.sub_label.hide()

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Card(QFrame):
    """Панель-карточка с необязательным заголовком."""

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

    def add_divider(self):
        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        self.body.addWidget(line)


class EmptyState(QWidget):
    """Заглушка для пустых списков: заголовок, пояснение, действие."""

    def __init__(self, title: str, description: str = "", button: str = "",
                 parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "h2")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.title_label)
        self.desc_label = QLabel(description)
        self.desc_label.setProperty("role", "dim")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumWidth(460)
        v.addWidget(self.desc_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.button = None
        if button:
            self.button = QPushButton(button)
            self.button.setProperty("accent", "true")
            v.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_text(self, title: str, description: str = ""):
        self.title_label.setText(title)
        self.desc_label.setText(description)


def mono_font(size: int = 12) -> QFont:
    for family in ("Cascadia Mono", "Consolas", "Courier New"):
        f = QFont(family, size)
        if f.exactMatch() or family == "Courier New":
            return f
    return QFont("monospace", size)


def setup_table(table: QTableWidget, row_height: int = 30,
                alternating: bool = True) -> None:
    """Единые настройки всех таблиц приложения."""
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setShowGrid(False)
    table.setAlternatingRowColors(alternating)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setWordWrap(False)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


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
    """Строка «подпись — поле — пояснение» для экрана настроек."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    row = QHBoxLayout()
    row.setSpacing(10)
    lab = QLabel(caption)
    lab.setMinimumWidth(190)
    lab.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    row.addWidget(lab)
    row.addWidget(widget, stretch=1)
    v.addLayout(row)
    if hint:
        h = QLabel(hint)
        h.setProperty("role", "dim")
        h.setWordWrap(True)
        h.setContentsMargins(200, 0, 0, 0)
        v.addWidget(h)
    return w
