"""Диалоги этапа 5: перевод через API, ключи провайдеров, пакетный мастер."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ck3loc.providers.registry import (
    PROVIDERS,
    get_api_key,
    make_provider,
    set_api_key,
)


def _provider_combo() -> QComboBox:
    combo = QComboBox()
    for name, cls in PROVIDERS.items():
        wave = "волна 1" if cls.info.wave == 1 else "LLM"
        combo.addItem(f"{cls.info.title} ({wave})", name)
    return combo


class KeysDialog(QDialog):
    """Сохранение API-ключей в Windows Credential Manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ключи API")
        self.resize(520, 160)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            "Ключ хранится в защищённом хранилище Windows, не в файлах."
        ))
        row = QHBoxLayout()
        self.combo = _provider_combo()
        self.combo.currentIndexChanged.connect(self._refresh_state)
        row.addWidget(self.combo)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Вставьте API-ключ…")
        row.addWidget(self.key_edit, stretch=1)
        v.addLayout(row)
        self.state = QLabel()
        v.addWidget(self.state)
        btns = QHBoxLayout()
        save = QPushButton("Сохранить")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        clear = QPushButton("Удалить ключ")
        clear.clicked.connect(self._clear)
        btns.addWidget(clear)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        v.addLayout(btns)
        self._refresh_state()

    def _refresh_state(self):
        name = self.combo.currentData()
        self.state.setText(
            "Ключ сохранён." if get_api_key(name) else "Ключ не задан."
        )

    def _save(self):
        name = self.combo.currentData()
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Ключи API", "Введите ключ.")
            return
        set_api_key(name, key)
        self.key_edit.clear()
        self._refresh_state()

    def _clear(self):
        set_api_key(self.combo.currentData(), "")
        self._refresh_state()


class _TranslateWorker(QThread):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, mod_id: str, provider_name: str, what: str):
        super().__init__()
        self.mod_id = mod_id
        self.provider_name = provider_name
        self.what = what

    def run(self):
        from ck3loc.core import db
        from ck3loc.core.glossary_seed import seed_glossary
        from ck3loc.core.ops import load_project_context, rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, translate_rows

        conn = db.connect()
        try:
            seed_glossary(conn)
            ctx = load_project_context(conn, self.mod_id)
            if ctx is None:
                self.failed.emit("Мод не найден.")
                return
            rows = rows_to_translate(ctx, self.what)
            if not rows:
                self.failed.emit("Переводить нечего — всё актуально.")
                return
            provider = make_provider(self.provider_name)
            vl = build_vanilla_lookup(ctx.project["source_lang"],
                                      ctx.project["target_lang"])
            stats = translate_rows(
                ctx, rows, provider,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                vanilla_lookup=vl,
            )
            self.done.emit(stats)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
        finally:
            conn.close()


class TranslateDialog(QDialog):
    """Перевод одного мода через встроенный провайдер."""

    def __init__(self, mod_id: str, estimate_text: str, parent=None):
        super().__init__(parent)
        self.mod_id = mod_id
        self.setWindowTitle("Перевести через API")
        self.resize(560, 320)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(estimate_text))
        row = QHBoxLayout()
        row.addWidget(QLabel("Провайдер:"))
        self.combo = _provider_combo()
        row.addWidget(self.combo, stretch=1)
        v.addLayout(row)
        self.progress = QProgressBar()
        v.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, stretch=1)
        btns = QHBoxLayout()
        self.btn_go = QPushButton("Перевести")
        self.btn_go.clicked.connect(self.start)
        btns.addWidget(self.btn_go)
        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.accept)
        btns.addWidget(self.btn_close)
        v.addLayout(btns)
        self.worker: _TranslateWorker | None = None
        self.stats = None

    def start(self):
        name = self.combo.currentData()
        if PROVIDERS[name].info.needs_key and not get_api_key(name):
            QMessageBox.warning(
                self, "Нет ключа",
                "Для этого провайдера не задан API-ключ.\n"
                "Главное окно → «Ключи API…».",
            )
            return
        self.btn_go.setEnabled(False)
        self.worker = _TranslateWorker(self.mod_id, name, "all")
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _on_done(self, stats):
        self.stats = stats
        self.btn_go.setEnabled(True)
        self.log.appendPlainText(
            f"Готово. Ваниль CK3: {stats.from_vanilla}, память переводов: "
            f"{stats.from_memory}, API: {stats.from_api}, "
            f"ошибок: {len(stats.failed)}"
        )
        for key, reason in stats.failed[:10]:
            self.log.appendPlainText(f"  {key}: {reason}")
        self.log.appendPlainText(
            "Закройте окно и нажмите «Записать перевод», чтобы перевод попал в игру."
        )

    def _on_failed(self, msg: str):
        self.btn_go.setEnabled(True)
        self.log.appendPlainText(f"Ошибка: {msg}")


class _BatchWorker(QThread):
    line = Signal(str)
    progress = Signal(int, int)
    done = Signal()

    def __init__(self, provider_name: str):
        super().__init__()
        self.provider_name = provider_name

    def run(self):
        from ck3loc.core import db
        from ck3loc.core.glossary_seed import seed_glossary
        from ck3loc.core.ops import load_project_context, rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, translate_rows
        from ck3loc.core.scanner import scan_mod
        from ck3loc.core.steam import list_workshop_mod_dirs, workshop_content_dirs
        from ck3loc.core.vanilla import game_languages
        from ck3loc.core.writer import apply_write_plan, build_write_plan

        conn = db.connect()
        try:
            seed_glossary(conn)
            provider = make_provider(self.provider_name)
            langs = game_languages()
            queue = []
            for mod_dir in list_workshop_mod_dirs(workshop_content_dirs()):
                scan = scan_mod(mod_dir, langs)
                if not scan.has_localization:
                    continue
                src = scan.best_source_language("english") or "english"
                translated, of = scan.coverage("russian", src)
                if of > 0 and translated == 0:
                    queue.append(mod_dir)
            self.line.emit(f"Модов без русского: {len(queue)}")
            for i, mod_dir in enumerate(queue, start=1):
                self.progress.emit(i, len(queue))
                ctx = load_project_context(conn, mod_dir.name, mod_dir=mod_dir)
                rows = rows_to_translate(ctx, "missing")
                self.line.emit(f"[{i}/{len(queue)}] {ctx.scan.name}: {len(rows)} строк")
                vl = build_vanilla_lookup(ctx.project["source_lang"], "russian")
                stats = translate_rows(ctx, rows, provider, vanilla_lookup=vl)
                self.line.emit(
                    f"    ваниль {stats.from_vanilla}, память {stats.from_memory}, "
                    f"API {stats.from_api}, ошибок {len(stats.failed)}"
                )
                ctx = load_project_context(conn, mod_dir.name, mod_dir=mod_dir)
                plan = build_write_plan(ctx.scan, ctx.project, ctx.units)
                if plan.total_keys:
                    apply_write_plan(conn, ctx.project_id, plan, ctx.scan, ctx.units)
                    self.line.emit(f"    записано ключей: {plan.total_keys}")
            self.done.emit()
        except Exception as e:  # noqa: BLE001
            self.line.emit(f"Ошибка: {e}")
            self.done.emit()
        finally:
            conn.close()


class BatchDialog(QDialog):
    """Пакетный мастер: перевести и записать все моды без русского."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Перевести все моды без русского")
        self.resize(640, 420)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            "Все моды без русского будут переведены выбранным провайдером\n"
            "и записаны внутрь модов. Ваниль CK3 и память переводов — бесплатно."
        ))
        row = QHBoxLayout()
        row.addWidget(QLabel("Провайдер:"))
        self.combo = _provider_combo()
        row.addWidget(self.combo, stretch=1)
        v.addLayout(row)
        self.progress = QProgressBar()
        v.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, stretch=1)
        btns = QHBoxLayout()
        self.btn_go = QPushButton("Запустить")
        self.btn_go.clicked.connect(self.start)
        btns.addWidget(self.btn_go)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        v.addLayout(btns)
        self.worker: _BatchWorker | None = None

    def start(self):
        name = self.combo.currentData()
        if PROVIDERS[name].info.needs_key and not get_api_key(name):
            QMessageBox.warning(
                self, "Нет ключа",
                "Для этого провайдера не задан API-ключ.\n"
                "Главное окно → «Ключи API…».",
            )
            return
        self.btn_go.setEnabled(False)
        self.worker = _BatchWorker(name)
        self.worker.line.connect(self.log.appendPlainText)
        self.worker.progress.connect(
            lambda i, t: (self.progress.setMaximum(t), self.progress.setValue(i))
        )
        self.worker.done.connect(lambda: self.btn_go.setEnabled(True))
        self.worker.start()
