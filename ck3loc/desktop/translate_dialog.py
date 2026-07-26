"""Диалоги перевода: один мод через API и пакетный режим."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ck3loc.core import settings
from ck3loc.desktop.widgets import Card
from ck3loc.desktop.workers import BatchWorker, TranslateWorker
from ck3loc.providers.registry import PROVIDERS, get_api_key


def provider_combo() -> QComboBox:
    combo = QComboBox()
    for name, cls in PROVIDERS.items():
        mark = "" if cls.info.wave == 1 else "  · нейросеть"
        combo.addItem(f"{cls.info.title}{mark}", name)
    saved = settings.get("provider")
    idx = combo.findData(saved)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo


def check_key(parent, name: str) -> bool:
    if PROVIDERS[name].info.needs_key and not get_api_key(name):
        QMessageBox.warning(
            parent, "Нет ключа",
            f"Для «{PROVIDERS[name].info.title}» не задан ключ API.\n\n"
            f"Настройки → Ключи API переводчиков.\n"
            f"Либо переводите бесплатно: «Выгрузить задание для нейросети».",
        )
        return False
    return True


class TranslateDialog(QDialog):
    """Перевод одного мода встроенным провайдером."""

    def __init__(self, mod_id: str, estimate_html: str, parent=None):
        super().__init__(parent)
        self.mod_id = mod_id
        self.stats = None
        self.setWindowTitle("Перевод через API")
        self.resize(660, 440)
        v = QVBoxLayout(self)
        v.setSpacing(12)

        est = Card("Смета до запуска")
        lab = QLabel(estimate_html)
        lab.setWordWrap(True)
        est.add(lab)
        v.addWidget(est)

        row = QHBoxLayout()
        row.addWidget(QLabel("Переводчик:"))
        self.combo = provider_combo()
        row.addWidget(self.combo, stretch=1)
        v.addLayout(row)

        self.progress = QProgressBar()
        v.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, stretch=1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_go = QPushButton("Перевести")
        self.btn_go.setProperty("accent", "true")
        self.btn_go.clicked.connect(self.start)
        btns.addWidget(self.btn_go)
        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.accept)
        btns.addWidget(self.btn_close)
        v.addLayout(btns)
        self.worker: TranslateWorker | None = None

    def start(self):
        name = self.combo.currentData()
        if not check_key(self, name):
            return
        settings.set_value("provider", name)
        cfg = settings.load()
        self.btn_go.setEnabled(False)
        self.log.appendPlainText("Перевод запущен…")
        self.worker = TranslateWorker(
            self.mod_id, name, "all", cfg["source_lang"], cfg["target_lang"]
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.line.connect(self.log.appendPlainText)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _on_done(self, stats):
        self.btn_go.setEnabled(True)
        self.stats = stats
        if stats is None:
            return
        self.log.appendPlainText(
            f"Готово. Ваниль CK3: {stats.from_vanilla} · память переводов: "
            f"{stats.from_memory} · через API: {stats.from_api} · "
            f"не удалось: {len(stats.failed)}"
        )
        for key, reason in stats.failed[:10]:
            self.log.appendPlainText(f"   ✗ {key}: {reason}")
        self.log.appendPlainText(
            "Закройте окно и нажмите «Записать перевод в игру»."
        )


class BatchDialog(QDialog):
    """Пакетный перевод всех модов без целевого языка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Перевести все моды, где перевода нет")
        self.resize(720, 520)
        v = QVBoxLayout(self)
        v.setSpacing(12)

        info = Card("Что произойдёт")
        lab = QLabel(
            "Все моды, где целевого языка нет совсем, будут переведены выбранным "
            "переводчиком и записаны по очереди.\n\n"
            "Строки, совпадающие с ванильной локализацией CK3 и с памятью "
            "переводов, подставляются бесплатно и в API не отправляются.\n"
            "Процесс можно остановить в любой момент — сделанное сохранится."
        )
        lab.setWordWrap(True)
        info.add(lab)
        v.addWidget(info)

        row = QHBoxLayout()
        row.addWidget(QLabel("Переводчик:"))
        self.combo = provider_combo()
        row.addWidget(self.combo, stretch=1)
        v.addLayout(row)

        self.progress = QProgressBar()
        v.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, stretch=1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_go = QPushButton("Запустить")
        self.btn_go.setProperty("accent", "true")
        self.btn_go.clicked.connect(self.start)
        btns.addWidget(self.btn_go)
        self.btn_stop = QPushButton("Остановить")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        btns.addWidget(self.btn_stop)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        v.addLayout(btns)
        self.worker: BatchWorker | None = None

    def start(self):
        name = self.combo.currentData()
        if not check_key(self, name):
            return
        settings.set_value("provider", name)
        cfg = settings.load()
        self.btn_go.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker = BatchWorker(name, cfg["source_lang"], cfg["target_lang"])
        self.worker.line.connect(self.log.appendPlainText)
        self.worker.progress.connect(
            lambda i, t: (self.progress.setMaximum(t), self.progress.setValue(i))
        )
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.log.appendPlainText("Останавливаю после текущего мода…")

    def _on_done(self):
        self.btn_go.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log.appendPlainText("Пакетный перевод завершён.")
