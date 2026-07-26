"""Оформление приложения: палитры, таблица стилей Qt, иконка.

Шкала отступов: 6 / 10 / 16 / 22. Скругления: 6 (элементы), 10 (карточки).
"""

from __future__ import annotations

DARK = {
    "bg": "#15171c",
    "panel": "#1d2027",
    "panel2": "#252932",
    "panel3": "#2d323c",
    "border": "#2e333d",
    "text": "#e9ebef",
    "text_dim": "#8d95a3",
    "accent": "#d4a94f",
    "accent_dim": "#a8842f",
    "accent_text": "#17191e",
    "ok": "#61ab72",
    "warn": "#d09a45",
    "err": "#cd6a6a",
    "info": "#5e93b5",
    "sel": "#304a6e",
}

LIGHT = {
    "bg": "#f4f5f7",
    "panel": "#ffffff",
    "panel2": "#eef0f4",
    "panel3": "#e3e7ed",
    "border": "#d9dde4",
    "text": "#1b1e24",
    "text_dim": "#616a78",
    "accent": "#9c7526",
    "accent_dim": "#c9a24d",
    "accent_text": "#ffffff",
    "ok": "#2f7a41",
    "warn": "#96661a",
    "err": "#a33b3b",
    "info": "#2f6183",
    "sel": "#d3e2f5",
}

MONO = "'Cascadia Mono', 'Consolas', monospace"


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
    QLabel[role="h1"] {{ font-size: 21px; font-weight: 600; }}
    QLabel[role="h2"] {{ font-size: 14px; font-weight: 600; }}
    QLabel[role="dim"] {{ color: {c['text_dim']}; }}
    QLabel[role="mono"] {{ font-family: {MONO}; font-size: 12px; }}

    /* боковая навигация */
    QFrame#Sidebar {{
        background: {c['panel']};
        border-right: 1px solid {c['border']};
    }}
    QLabel#Logo {{
        font-size: 15px; font-weight: 700; padding: 0 16px;
        color: {c['text']};
    }}
    QLabel#LogoSub {{
        font-size: 11px; padding: 0 16px 16px; color: {c['text_dim']};
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
    QLabel#SidebarNote {{
        color: {c['text_dim']};
        font-size: 11px;
        padding: 12px 16px 0;
        border-top: 1px solid {c['border']};
    }}

    /* карточки и плитки */
    QFrame#Tile {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QFrame#Tile:hover {{ border: 1px solid {c['accent_dim']}; }}
    QFrame#Tile[active="true"] {{
        border: 1px solid {c['accent']};
        background: {c['panel2']};
    }}
    QFrame#Card {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QFrame#Divider {{ background: {c['border']}; max-height: 1px; border: none; }}

    /* кнопки */
    QPushButton {{
        background: {c['panel2']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 7px 14px;
        min-height: 18px;
    }}
    QPushButton:hover {{ background: {c['panel3']}; border-color: {c['accent_dim']}; }}
    QPushButton:pressed {{ background: {c['panel']}; }}
    QPushButton:disabled {{ color: {c['text_dim']}; background: {c['panel']}; }}
    QPushButton[accent="true"] {{
        background: {c['accent']};
        border: 1px solid {c['accent']};
        color: {c['accent_text']};
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{
        background: {c['accent_dim']}; border-color: {c['accent_dim']};
    }}
    QPushButton[accent="true"]:disabled {{
        background: {c['panel2']}; border-color: {c['border']};
        color: {c['text_dim']};
    }}
    QPushButton#LinkButton {{
        background: transparent; border: none; color: {c['text_dim']};
        padding: 4px 8px; text-align: left;
    }}
    QPushButton#LinkButton:hover {{ color: {c['text']}; }}

    /* поля ввода */
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 9px;
        selection-background-color: {c['sel']};
        selection-color: {c['text']};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border-color: {c['accent_dim']};
    }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {c['text_dim']}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        selection-background-color: {c['sel']};
        outline: none;
        padding: 4px;
    }}

    /* таблицы */
    QTableWidget, QTableView {{
        background: {c['panel']};
        alternate-background-color: {c['panel2']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        gridline-color: transparent;
        selection-background-color: {c['sel']};
        selection-color: {c['text']};
        outline: none;
    }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{
        background: {c['panel2']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 9px 8px;
        font-weight: 600;
        font-size: 12px;
        color: {c['text_dim']};
    }}
    QHeaderView::section:first {{ border-top-left-radius: 10px; }}
    QHeaderView::section:last {{ border-top-right-radius: 10px; }}
    QTableWidget::item {{ padding: 6px 8px; border: none; }}
    QTableCornerButton::section {{ background: {c['panel2']}; border: none; }}

    /* вкладки */
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 10px;
        background: {c['panel']};
        top: -1px;
    }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: transparent;
        color: {c['text_dim']};
        padding: 9px 18px;
        margin-right: 2px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {c['text']};
        border-bottom: 2px solid {c['accent']};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{ color: {c['text']}; }}

    /* прогресс */
    QProgressBar {{
        background: {c['panel2']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        height: 14px;
        text-align: center;
        font-size: 11px;
        color: {c['text_dim']};
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
    QProgressBar#Coverage {{ height: 8px; border: none; background: {c['panel3']}; }}
    QProgressBar#Coverage::chunk {{ background: {c['ok']}; border-radius: 4px; }}

    /* полосы прокрутки */
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
    QScrollBar::handle:vertical {{
        background: {c['border']}; border-radius: 5px; min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['text_dim']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
    QScrollBar::handle:horizontal {{
        background: {c['border']}; border-radius: 5px; min-width: 32px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c['text_dim']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollArea {{ border: none; background: transparent; }}

    /* выпадающее меню фильтров */
    QToolButton {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 7px 12px;
        text-align: left;
    }}
    QToolButton:hover {{ border-color: {c['accent_dim']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QMenu {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 14px 7px 30px;
        border-radius: 5px;
        color: {c['text']};
    }}
    QMenu::item:selected {{ background: {c['panel3']}; }}
    QMenu::separator {{
        height: 1px; background: {c['border']}; margin: 6px 8px;
    }}
    QMenu::indicator {{
        width: 14px; height: 14px; left: 9px; border-radius: 4px;
        border: 1px solid {c['border']}; background: {c['panel2']};
    }}
    QMenu::indicator:checked {{
        background: {c['accent']}; border-color: {c['accent']};
    }}

    /* прочее */
    QSplitter::handle {{ background: {c['border']}; height: 1px; }}
    QStatusBar {{
        background: {c['panel']};
        border-top: 1px solid {c['border']};
        color: {c['text_dim']};
    }}
    QStatusBar::item {{ border: none; }}
    QToolTip {{
        background: {c['panel3']}; color: {c['text']};
        border: 1px solid {c['border']}; padding: 6px 8px; border-radius: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 4px;
        border: 1px solid {c['border']}; background: {c['panel']};
    }}
    QCheckBox::indicator:checked {{
        background: {c['accent']}; border-color: {c['accent']};
    }}
    QMessageBox, QDialog {{ background: {c['bg']}; }}
    QMessageBox QLabel {{ color: {c['text']}; }}
    """


def make_app_icon(theme: str = "dark"):
    """Иконка приложения: золотой щит с буквами CK."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QIcon,
        QPainter,
        QPainterPath,
        QPixmap,
    )

    c = palette(theme)
    icon = QIcon()
    for size in (16, 32, 64, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = size
        path = QPainterPath()
        m = s * 0.08
        path.moveTo(m, m)
        path.lineTo(s - m, m)
        path.lineTo(s - m, s * 0.58)
        path.quadTo(s - m, s - m, s / 2, s - m)
        path.quadTo(m, s - m, m, s * 0.58)
        path.closeSubpath()
        p.fillPath(path, QBrush(QColor(c["accent"])))
        if s >= 32:
            p.setPen(QColor(c["accent_text"]))
            f = QFont("Segoe UI", int(s * 0.34), QFont.Weight.Bold)
            p.setFont(f)
            p.drawText(QRectF(0, 0, s, s * 0.92),
                       Qt.AlignmentFlag.AlignCenter, "CK")
        p.end()
        icon.addPixmap(pix)
    return icon
