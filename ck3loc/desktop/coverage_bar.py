"""Полоска источников перевода: процент и из чего он складывается.

Сегменты не пересекаются и в сумме дают всю локализацию мода, поэтому
складывать числа в уме не нужно — картинка отвечает на вопрос
«эти 100% чьи?» без наведения мыши.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from ck3loc.core.i18n import tr
from ck3loc.desktop.theme import palette

# вид сегмента → (ключ цвета, подпись)
SEGMENTS = {
    "own": ("text_dim", "перевод автора мода"),
    "external": ("info", "мод-русификатор"),
    "mine": ("accent", "ваш перевод"),
    "stale": ("warn", "устарело"),
    "missing": ("err", "не хватает"),
}

# роль данных, в которой ячейка хранит [(вид, количество), …]
SEGMENTS_ROLE = Qt.ItemDataRole.UserRole + 10


def segment_color(kind: str, theme: str) -> QColor:
    key = SEGMENTS.get(kind, ("text_dim", ""))[0]
    return QColor(palette(theme)[key])


def format_percent(translated: int, total: int) -> str:
    """«100%» только когда переведено действительно всё, «0%» — когда ничего.

    Иначе округление даёт «100%» рядом с «1 пропущено».
    """
    if not total:
        return "—"
    if translated >= total:
        return "100%"
    if translated <= 0:
        return "0%"
    percent = round(100.0 * translated / total)
    return f"{min(99, max(1, percent))}%"


def describe(segments: list[tuple[str, int]]) -> str:
    """Расшифровка словами — для подсказки и карточки мода."""
    parts = [
        f"{tr(SEGMENTS[kind][1])}: {count}"
        for kind, count in segments if count
    ]
    return " · ".join(parts) if parts else "нет данных"


def paint_bar(painter: QPainter, rect: QRectF, segments, theme: str,
              radius: float = 2.0) -> None:
    total = sum(count for _kind, count in segments)
    if total <= 0:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    x = rect.left()
    remaining = rect.width()
    for i, (kind, count) in enumerate(segments):
        if count <= 0:
            continue
        last = i == len(segments) - 1
        width = remaining if last else rect.width() * count / total
        painter.setBrush(segment_color(kind, theme))
        painter.drawRoundedRect(
            QRectF(x, rect.top(), max(1.0, width), rect.height()),
            radius, radius,
        )
        x += width
        remaining -= width
    painter.restore()


class CoverageDelegate(QStyledItemDelegate):
    """Ячейка столбца «Переведено»: процент и полоска под ним."""

    BAR_HEIGHT = 5
    BAR_BOTTOM = 7      # отступ полоски от низа ячейки

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme

    def paint(self, painter, option, index):
        segments = index.data(SEGMENTS_ROLE)
        if not segments:
            super().paint(painter, option, index)
            return
        # ячейку рисуем целиком сами: базовый делегат игнорирует
        # уменьшённый прямоугольник, и текст наезжает на полоску
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )

        painter.save()
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        painter.setPen(
            brush.color() if brush is not None
            else QColor(palette(self.theme)["text"])
        )
        painter.drawText(
            option.rect.adjusted(6, 1, -8, -(self.BAR_HEIGHT + self.BAR_BOTTOM)),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()

        paint_bar(
            painter,
            QRectF(
                option.rect.left() + 8,
                option.rect.bottom() - self.BAR_HEIGHT - 4,
                option.rect.width() - 16,
                self.BAR_HEIGHT,
            ),
            segments,
            self.theme,
        )


class SegmentBar(QWidget):
    """Крупная полоска источников — для карточки мода."""

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.segments: list[tuple[str, int]] = []
        self.setFixedHeight(10)

    def set_segments(self, segments: list[tuple[str, int]]):
        self.segments = list(segments)
        self.setToolTip(describe(self.segments))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        paint_bar(painter, QRectF(0, 1, self.width(), self.height() - 2),
                  self.segments, self.theme, radius=4.0)
        painter.end()


class CoverageLegend(QWidget):
    """Легенда с цветами сегментов — под полоской в карточке мода."""

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.segments: list[tuple[str, int]] = []
        self.setFixedHeight(18)

    def set_segments(self, segments: list[tuple[str, int]]):
        self.segments = [(k, n) for k, n in segments if n]
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x = 0.0
        metrics = painter.fontMetrics()
        for kind, count in self.segments:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(segment_color(kind, self.theme))
            painter.drawRoundedRect(QRectF(x, 6.0, 8.0, 8.0), 2.0, 2.0)
            x += 12
            text = f"{tr(SEGMENTS[kind][1])}: {count}"
            painter.setPen(QColor(palette(self.theme)["text_dim"]))
            painter.drawText(QRectF(x, 0, metrics.horizontalAdvance(text) + 4,
                                    self.height()),
                             Qt.AlignmentFlag.AlignVCenter, text)
            x += metrics.horizontalAdvance(text) + 16
        painter.end()
