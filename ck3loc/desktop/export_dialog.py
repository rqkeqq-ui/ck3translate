"""Диалог выгрузки задания: выбор объёма и формата."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QSpinBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ck3loc.core.i18n import tr, tr_format
from ck3loc.core.ops import WHAT_ALL, WHAT_MISSING, WHAT_OUTDATED, WHAT_SELECTED, WHAT_SERVICE, WHAT_STALE
from ck3loc.desktop.widgets import Card


class ExportScopeDialog(QDialog):
    """Что именно выгружать: только недостающее или всё подряд."""

    def __init__(self, counts: dict[str, int], parent=None, *, ctx=None, keys=None):
        super().__init__(parent)
        self.setWindowTitle("Выгрузка задания для перевода")
        self.setSizeGripEnabled(True)
        self.setMinimumWidth(620)
        self.ctx, self.keys, self.counts = ctx, keys or set(), counts
        v = QVBoxLayout(self)
        v.setSpacing(12)

        card = Card("Что выгрузить")
        self.options: list[tuple[QRadioButton, str]] = []

        def add_option(text: str, what: str, hint: str, enabled: bool = True):
            radio = QRadioButton(tr_format("{label} — {count} строк",
                                               label=tr(text), count=counts.get(what, 0)))
            radio.setEnabled(enabled and counts.get(what, 0) > 0)
            card.add(radio)
            lab = QLabel(hint)
            lab.setProperty("role", "dim")
            lab.setWordWrap(True)
            lab.setContentsMargins(24, 0, 0, 6)
            card.add(lab)
            self.options.append((radio, what))

        add_option(
            'Выбранные строки', WHAT_SELECTED, 'Только выделенные ключи текущего исходника.',
        )
        add_option(
            "Только недостающие", WHAT_MISSING,
            "Строки, которых нет ни в переводе мода, ни в вашей базе. "
            "Обычный выбор: не тратит деньги и не трогает готовый перевод.",
        )
        add_option(
            "Недостающие и устаревшие", WHAT_OUTDATED,
            "Плюс строки, у которых автор мода изменил исходный текст "
            "после того, как вы их перевели.",
        )
        add_option(
            "Только устаревшие", WHAT_STALE,
            "Ничего нового, только освежить те, что разошлись с источником.",
        )
        add_option(
            "Непроверенный машинный перевод", WHAT_SERVICE,
            "Строки, переведённые Google, Bing, Яндексом, DeepL или Alibaba и не отмеченные вами как "
            "проверенные. Чтобы заменить их переводом нейросети, при загрузке отметьте замены.",
        )
        add_option(
            "Все строки", WHAT_ALL,
            "Все текущие ключи исходника, включая уже переведённые вами, автором "
            "или другим модом. Готовый перевод заменяется только теми строками, "
            "которые вы отметите при загрузке.",
        )
        v.addWidget(card)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Формат файла:"))
        self.fmt = QComboBox()
        self.fmt.addItem("JSONL — для нейросети в чате", "jsonl")
        self.fmt.addItem("XLIFF 2.1 — для переводческих программ", "xliff")
        self.fmt.addItem('CK3 YML', 'yml')
        fmt_row.addWidget(self.fmt, stretch=1)
        v.addLayout(fmt_row)
        from ck3loc.desktop.tasks import SplitControl
        self.splitter = SplitControl()
        v.addWidget(self.splitter)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        v.addWidget(self.preview)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton("Выгрузить…")
        self.btn_ok.setProperty("accent", "true")
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        v.addLayout(btns)

        # по умолчанию — первый доступный вариант, начиная с «недостающих»
        for radio, _what in self.options:
            if radio.isEnabled():
                radio.setChecked(True)
                break
        else:
            self.btn_ok.setEnabled(False)
        for radio, _ in self.options:
            radio.toggled.connect(self.update_preview)
        self.adjustSize()  # высота по содержимому: подсказки не обрезаются
        self.splitter.changed.connect(self.update_preview)
        self.fmt.currentIndexChanged.connect(self.update_preview)
        self.update_preview()

    def split_kwargs(self) -> dict:
        return self.splitter.kwargs()

    def archives(self):
        """Совместимость: число архивов при делении «на число архивов»."""
        return self.split_kwargs().get('archives')

    def part_size(self):
        """Совместимость: теперь задаётся число архивов, а не строк в файле."""
        return None

    def update_preview(self, *_):
        from ck3loc.core.exchange import describe_sizes, package_sizes, split_preview
        from ck3loc.core.ops import rows_to_translate
        if self.ctx:
            rows = rows_to_translate(self.ctx, self.scope(), self.keys)
            total, sizes = len(rows), split_preview([rows], **self.split_kwargs())
        else:
            total = self.counts.get(self.scope(), 0)
            split = self.split_kwargs()
            sizes = package_sizes(total, archives=1) if 'chars_per_archive' in split else package_sizes(total, **split)
        self.btn_ok.setEnabled(bool(sizes))
        self.preview.setText(tr_format('Строк: {n}. Будет создано ZIP-архивов: {parts} ({sizes} строк) '
                                       'и один файл с промптом рядом с ними.',
                                       n=total, parts=len(sizes), sizes=describe_sizes(sizes)))

    def scope(self) -> str:
        for radio, what in self.options:
            if radio.isChecked():
                return what
        return WHAT_MISSING

    def format(self) -> str:
        return self.fmt.currentData()
