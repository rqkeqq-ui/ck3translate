"""Оформление приложения: палитры и таблица стилей Qt."""

from __future__ import annotations

DARK = {
    "bg": "#1b1d22",
    "panel": "#23262d",
    "panel2": "#2b2f37",
    "border": "#343943",
    "text": "#e8e9ec",
    "text_dim": "#9aa0ab",
    "accent": "#c9a24d",
    "accent_dim": "#8c6f34",
    "ok": "#5aa469",
    "warn": "#c9903f",
    "err": "#c26060",
    "info": "#5a86a4",
    "sel": "#33507a",
}

LIGHT = {
    "bg": "#f3f4f6",
    "panel": "#ffffff",
    "panel2": "#f7f8fa",
    "border": "#d8dbe0",
    "text": "#1d2026",
    "text_dim": "#5f6672",
    "accent": "#8a6a1f",
    "accent_dim": "#c9a24d",
    "ok": "#2f7a41",
    "warn": "#9a6b16",
    "err": "#a33b3b",
    "info": "#2f6183",
    "sel": "#cfe0f5",
}


def palette(name: str) -> dict:
    return LIGHT if name == "light" else DARK


def stylesheet(name: str = "dark") -> str:
    c = palette(name)
    return f"""
    QWidget {{
        background: {c['bg']};
        color: {c['text']};
        font-family: 'Segoe UI', sans-serif;
        font-size: 13px;
    }}
    /* надписи и флажки не рисуют свой фон — иначе на карточках
       появляются тёмные прямоугольники поверх панели */
    QLabel, QCheckBox {{ background: transparent; }}
    QLabel[role="h1"] {{ font-size: 20px; font-weight: 600; }}
    QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
    QLabel[role="dim"] {{ color: {c['text_dim']}; }}

    /* боковая навигация */
    QFrame#Sidebar {{
        background: {c['panel']};
        border-right: 1px solid {c['border']};
    }}
    QPushButton#NavButton {{
        background: transparent;
        border: none;
        border-left: 3px solid transparent;
        padding: 11px 16px;
        text-align: left;
        font-size: 14px;
        color: {c['text_dim']};
    }}
    QPushButton#NavButton:hover {{ background: {c['panel2']}; color: {c['text']}; }}
    QPushButton#NavButton:checked {{
        background: {c['panel2']};
        border-left: 3px solid {c['accent']};
        color: {c['text']};
        font-weight: 600;
    }}

    /* карточки-плитки */
    QFrame#Tile {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}
    QFrame#Tile:hover {{ border: 1px solid {c['accent_dim']}; }}
    QFrame#Card {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}

    /* кнопки */
    QPushButton {{
        background: {c['panel2']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 7px 14px;
    }}
    QPushButton:hover {{ border-color: {c['accent_dim']}; }}
    QPushButton:pressed {{ background: {c['panel']}; }}
    QPushButton:disabled {{ color: {c['text_dim']}; border-color: {c['border']}; }}
    QPushButton[accent="true"] {{
        background: {c['accent']};
        border: 1px solid {c['accent']};
        color: #16181c;
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{ background: {c['accent_dim']}; }}
    QPushButton[accent="true"]:disabled {{ background: {c['panel2']}; color: {c['text_dim']}; }}

    /* поля ввода */
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 8px;
        selection-background-color: {c['sel']};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border-color: {c['accent_dim']};
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        selection-background-color: {c['sel']};
    }}

    /* таблицы */
    QTableWidget, QTableView {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        gridline-color: {c['border']};
        selection-background-color: {c['sel']};
        selection-color: {c['text']};
    }}
    QHeaderView::section {{
        background: {c['panel2']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 8px 6px;
        font-weight: 600;
        color: {c['text_dim']};
    }}
    QTableWidget::item {{ padding: 4px 6px; }}

    /* вкладки */
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 8px;
        background: {c['panel']};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {c['text_dim']};
        padding: 8px 16px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {c['text']};
        border-bottom: 2px solid {c['accent']};
        font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {c['text']}; }}

    /* прочее */
    QProgressBar {{
        background: {c['panel2']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        height: 16px;
        text-align: center;
        color: {c['text_dim']};
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {c['border']}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['text_dim']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{
        background: {c['border']}; border-radius: 5px; min-width: 30px;
    }}
    QSplitter::handle {{ background: {c['border']}; }}
    QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['border']}; }}
    QToolTip {{
        background: {c['panel2']}; color: {c['text']};
        border: 1px solid {c['border']}; padding: 5px;
    }}
    QCheckBox::indicator {{
        width: 15px; height: 15px; border-radius: 4px;
        border: 1px solid {c['border']}; background: {c['panel']};
    }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    """
