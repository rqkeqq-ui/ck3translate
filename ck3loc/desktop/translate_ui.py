"""Перевод готового дерева виджетов.

Ключ перевода — исходный русский текст, поэтому отдельная разметка кода
не нужна: проходим по виджетам и подменяем надписи. Исходный текст
запоминается в свойстве виджета, чтобы язык можно было менять на лету.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from ck3loc.core.i18n import tr

_SRC = "i18n_src"
_SRC_TIP = "i18n_tip"
_SRC_PLACEHOLDER = "i18n_ph"
_SRC_ITEMS = "i18n_items"
_SRC_TABS = "i18n_tabs"
_SRC_HEADERS = "i18n_headers"


def _source(widget: QWidget, prop: str, current):
    """Вернуть исходный (русский) текст, запомнив его при первом проходе."""
    saved = widget.property(prop)
    if saved is None:
        widget.setProperty(prop, current)
        return current
    return saved


def translate_widget(w: QWidget) -> None:
    if isinstance(w, QLabel):
        src = _source(w, _SRC, w.text())
        if src and "<" not in src:      # размеченные надписи собираются в коде
            w.setText(tr(src))
    elif isinstance(w, QAbstractButton):
        src = _source(w, _SRC, w.text())
        if src:
            w.setText(tr(src))
    elif isinstance(w, QGroupBox):
        w.setTitle(tr(_source(w, _SRC, w.title())))

    if isinstance(w, QComboBox):
        items = _source(w, _SRC_ITEMS,
                        [w.itemText(i) for i in range(w.count())])
        for i, text in enumerate(items):
            if i < w.count():
                w.setItemText(i, tr(text))
    if isinstance(w, (QLineEdit, QPlainTextEdit, QTextEdit)):
        ph = _source(w, _SRC_PLACEHOLDER, w.placeholderText())
        if ph:
            w.setPlaceholderText(tr(ph))
    if isinstance(w, QTabWidget):
        tabs = _source(w, _SRC_TABS,
                       [w.tabText(i) for i in range(w.count())])
        for i, text in enumerate(tabs):
            if i < w.count():
                w.setTabText(i, tr(text))
    if isinstance(w, QTableWidget):
        headers = _source(
            w, _SRC_HEADERS,
            [w.horizontalHeaderItem(i).text() if w.horizontalHeaderItem(i)
             else "" for i in range(w.columnCount())],
        )
        for i, text in enumerate(headers):
            item = w.horizontalHeaderItem(i)
            if item is not None and text:
                item.setText(tr(text))

    tip = w.toolTip()
    saved_tip = w.property(_SRC_TIP)
    if tip or saved_tip:
        w.setToolTip(tr(_source(w, _SRC_TIP, tip)))


def translate_tree(root: QWidget) -> None:
    """Перевести окно целиком, включая все вложенные виджеты."""
    translate_widget(root)
    for child in root.findChildren(QWidget):
        translate_widget(child)
    window_title = root.property("i18n_title")
    if window_title is None:
        window_title = root.windowTitle()
        root.setProperty("i18n_title", window_title)
    if window_title:
        root.setWindowTitle(tr(window_title))
