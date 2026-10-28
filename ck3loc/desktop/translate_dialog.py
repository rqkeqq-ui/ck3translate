"""Перевод внутри приложения: один мод (TranslateDialog) и общие настройки.

Порядок одинаковый везде: выбрать строки → посмотреть задание → запустить →
проверить результат → применить выбранное → записать в игру. Открытие окна
не отправляет запросов; тяжёлая подготовка (ванильный словарь CK3) идёт в
фоне, чтобы окно не зависало.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ck3loc.core import settings
from ck3loc.core.i18n import tr, tr_format
from ck3loc.desktop.workers import TranslateWorker
from ck3loc.providers.registry import PROVIDERS, get_api_key, key_required

PREVIEW_LIMIT = 1000

# Объяснения к «?» в окне перевода — простыми словами, без терминов.
HELP = {
    'provider': 'Кто переводит. Варианты «бесплатно» (Google, Bing, Яндекс, Alibaba) работают без ключа и '
                'регистрации, быстро, но дословно. Нейросети (ChatGPT, Claude, DeepSeek и другие) переводят '
                'точнее и понимают контекст, но нужна подписка или ключ API.',
    'size': 'Сколько строк отправлять за один раз. Для нейросетей больше строк — быстрее и дешевле, но слишком '
            'большой запрос модель может не дописать; 20–40 строк обычно безопасно. Бесплатные переводчики всё '
            'равно переводят по одной строке.',
    'workers': 'Сколько запросов отправлять одновременно. 2–4 ускоряют перевод через платный API или свой '
               'сервер. Бесплатные переводчики и бесплатные тарифы за это блокируют — для них оставьте 1.',
    'pause': 'Сколько секунд ждать между запросами. Нужно, если сервис пишет о лимите («слишком много '
             'запросов»): поставьте 2–5 секунд. Обычно оставьте 0.',
    'reuse': 'Перевод, который уже есть, подставляется сразу — без запроса к переводчику и бесплатно. '
             'Наведите на «?» у каждого пункта, чтобы узнать, откуда он берётся.',
    'use_vanilla': 'Если точно такая же фраза есть в самой игре Crusader Kings 3, берётся официальный перевод '
                   'Paradox. Бесплатно, без запроса и одинаково с игрой (например, «Duke» → «Герцог»).',
    'use_memory': 'Если вы уже переводили точно такую же фразу — в этом или другом моде, — берётся тот перевод. '
                  'Экономит запросы, и одинаковые фразы переведены одинаково.',
    'allow_service_memory': 'Разрешить брать из памяти и машинный перевод (Google, Bing и другие), который вы '
                            'ещё не проверили. Включено — меньше запросов. Выключено — такие фразы переведёт '
                            'выбранный переводчик заново. Для перевода нейросетью лучше выключить.',
    'retranslate': 'Ничего не подставлять: каждая строка уходит выбранному переводчику, даже если готовый '
                   'перевод есть в игре или в памяти. Включайте, чтобы исправить или заменить перевод.',
}


def provider_combo() -> QComboBox:
    combo = QComboBox()
    for name, cls in PROVIDERS.items():
        mark = "" if cls.info.wave == 1 or name == "chatgpt" else "  · " + tr("нейросеть")
        combo.addItem(f"{tr(cls.info.title)}{mark}", name)
    saved = settings.get("provider")
    idx = combo.findData(saved)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo


def check_key(parent, name: str) -> bool:
    if name == 'chatgpt':
        from ck3loc.providers import chatgpt
        if not chatgpt.is_signed_in():
            QMessageBox.information(parent, 'ChatGPT', tr('Нажмите «Войти через ChatGPT» в этом окне — '
                                                          'вход откроется в браузере.'))
            return False
        if not settings.get('chatgpt_model'):
            QMessageBox.information(parent, 'ChatGPT', tr('Выберите модель ChatGPT из списка в этом окне.'))
            return False
        return True
    if key_required(name) and not get_api_key(name):
        QMessageBox.warning(
            parent, tr("Нет ключа"),
            tr_format("Для «{provider}» не задан ключ API.\n\nНастройки → Ключи API переводчиков.\n"
                      "Либо переводите бесплатно: «Выгрузить задание для нейросети».",
                      provider=tr(PROVIDERS[name].info.title)),
        )
        return False
    return True


class VanillaWarmup(QThread):
    """Один раз за запуск разобрать ванильную локализацию CK3 (секунды) в фоне."""

    def __init__(self, source_lang: str, target_lang: str, parent=None):
        super().__init__(parent)
        self.pair = (source_lang, target_lang)

    def run(self):
        from ck3loc.core.pipeline import build_vanilla_lookup
        try:
            build_vanilla_lookup(*self.pair)
        except OSError:
            pass


class TranslateOptions(QWidget):
    """Переводчик, вход ChatGPT, размер запроса и подстановки — общие для окон перевода."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from ck3loc.desktop.chatgpt_settings import ChatGPTAccountBar
        from ck3loc.desktop.widgets import HelpMark, with_help
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.help: dict[str, HelpMark] = {}

        def label(text: str, name: str, explanation: str) -> QWidget:
            box, self.help[name] = with_help(QLabel(tr(text)), tr(explanation))
            return box

        self.combo = provider_combo()
        form.addRow(label('Переводчик:', 'provider', HELP['provider']), self.combo)
        self.chatgpt = ChatGPTAccountBar(show_models=True)
        form.addRow('', self.chatgpt)
        self.size = QSpinBox()
        self.size.setRange(1, 250)
        self.size.setValue(40)
        self.size.setMaximumWidth(110)
        form.addRow(label('Не более строк на запрос:', 'size', HELP['size']), self.size)
        from ck3loc.core.pipeline import MAX_WORKERS
        self.workers = QSpinBox()
        self.workers.setRange(1, MAX_WORKERS)
        self.workers.setValue(int(settings.get('translate_workers') or 1))
        self.workers.setMaximumWidth(110)
        form.addRow(label('Параллельных запросов:', 'workers', HELP['workers']), self.workers)
        self.pause = QDoubleSpinBox()
        self.pause.setRange(0.0, 600.0)
        self.pause.setDecimals(1)
        self.pause.setSingleStep(0.5)
        self.pause.setValue(float(settings.get('translate_pause') or 0.0))
        self.pause.setSuffix(' ' + tr('с'))
        self.pause.setMaximumWidth(110)
        form.addRow(label('Пауза между запросами:', 'pause', HELP['pause']), self.pause)
        self.workers.valueChanged.connect(lambda value: settings.set_value('translate_workers', value))
        self.pause.valueChanged.connect(lambda value: settings.set_value('translate_pause', value))
        self.use_vanilla = QCheckBox(tr('Использовать ваниль CK3'))
        self.use_memory = QCheckBox(tr('Использовать память переводов'))
        self.allow_service_memory = QCheckBox(tr('Использовать непроверенные сервисные переводы из памяти'))
        self.retranslate = QCheckBox(tr('Перевести заново'))
        self.use_vanilla.setChecked(True)
        self.use_memory.setChecked(True)
        checks = QWidget()
        cv = QVBoxLayout(checks)
        cv.setContentsMargins(0, 0, 0, 0)
        for name, box in (('use_vanilla', self.use_vanilla), ('use_memory', self.use_memory),
                          ('allow_service_memory', self.allow_service_memory), ('retranslate', self.retranslate)):
            row, self.help[name] = with_help(box, tr(HELP[name]))
            cv.addWidget(row)
            box.toggled.connect(self._changed)
        form.addRow(label('Готовые переводы:', 'reuse', HELP['reuse']), checks)
        self.combo.currentIndexChanged.connect(self._changed)
        self.size.valueChanged.connect(self._changed)
        self.chatgpt.changed.connect(self.changed.emit)
        self._changed()

    def _changed(self, *_):
        is_chatgpt = self.provider() == 'chatgpt'
        self.chatgpt.setVisible(is_chatgpt)
        if is_chatgpt:
            self.chatgpt.refresh()
        reuse = not self.retranslate.isChecked()
        for box in (self.use_vanilla, self.use_memory, self.allow_service_memory):
            box.setEnabled(reuse)
        single = getattr(PROVIDERS[self.provider()], 'max_workers', None) == 1
        self.workers.setEnabled(not single)
        self.workers.setToolTip(tr('Бесплатный Google принимает только один запрос за раз: параллельные запросы '
                                   'приводят к блокировке по IP.') if single else '')
        self.changed.emit()

    def provider(self) -> str:
        return self.combo.currentData()

    def max_workers(self) -> int:
        """Сколько запросов уйдёт одновременно с учётом ограничения переводчика."""
        limit = getattr(PROVIDERS[self.provider()], 'max_workers', None)
        return min(self.workers.value(), limit) if limit else self.workers.value()

    def batch_size(self) -> int:
        return min(self.size.value(), PROVIDERS[self.provider()].batch_size)

    def options(self) -> dict:
        return dict(retranslate=self.retranslate.isChecked(), use_vanilla=self.use_vanilla.isChecked(),
                    use_memory=self.use_memory.isChecked(),
                    allow_service_memory=self.allow_service_memory.isChecked(),
                    rows_per_request=self.size.value(), workers=self.max_workers(),
                    request_pause=round(self.pause.value(), 1))

    def needs_vanilla(self) -> bool:
        return self.use_vanilla.isChecked() and not self.retranslate.isChecked()

    def model_name(self) -> str:
        name = self.provider()
        return settings.get('chatgpt_model' if name == 'chatgpt' else name + '_model') or ''

    def set_enabled(self, enabled: bool) -> None:
        for widget in (self.combo, self.size, self.workers, self.pause, self.use_vanilla, self.use_memory,
                       self.allow_service_memory, self.retranslate, self.chatgpt):
            widget.setEnabled(enabled)
        if enabled:
            self._changed()


def reuse_label(row: dict, provider_title: str) -> str:
    if row['reuse'] == 'vanilla':
        return tr('Ваниль CK3') + ': ' + row['reuse_target']
    if row['reuse'] == 'memory':
        return tr_format('Память ({provider})', provider=row['reuse_provider']) + ': ' + row['reuse_target']
    return tr_format('Запрос: {provider}', provider=provider_title)


class TranslateDialog(QDialog):
    """Exact selected scope, requests into drafts, explicit review and apply."""

    def __init__(self, mod_id, estimate_html='', parent=None, *, ctx=None, keys=None,
                 what='outdated', job_id=None):
        super().__init__(parent)
        from ck3loc.core import db
        from ck3loc.core.ops import load_project_context
        self.conn = db.connect()
        cfg = settings.load()
        self.ctx = load_project_context(self.conn, mod_id, cfg['source_lang'], cfg['target_lang'],
                                        mod_dir=ctx.scan.mod_dir if ctx else None)
        self.mod_id, self.keys, self.what = mod_id, set(keys or ()), what
        self.job_id, self.stats, self.worker = job_id, None, None
        self._background = False
        self.rows, self.planned = [], []
        self.setWindowTitle(tr('Задание перевода') + (f' — {self.ctx.scan.name}' if self.ctx else ''))
        self.setSizeGripEnabled(True)
        self.resize(1000, 720)
        v = QVBoxLayout(self)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel(tr('Какие строки:')))
        self.scope = QComboBox()
        for label, scope in [('Только недостающие', 'missing'), ('Недостающие и устаревшие', 'outdated'),
                             ('Только устаревшие', 'stale'), ('Непроверенный машинный перевод', 'service'),
                             ('Выбранные строки', 'selected'), ('Все строки', 'all')]:
            if scope == 'selected' and not self.keys:
                continue
            self.scope.addItem(tr(label), scope)
        self.scope.setCurrentIndex(max(0, self.scope.findData(what)))
        scope_row.addWidget(self.scope, 1)
        v.addLayout(scope_row)
        if job_id:
            self.scope.setEnabled(False)
            self.scope.setToolTip(tr('Продолжение задания: переводятся только оставшиеся строки.'))

        self.opts = TranslateOptions()
        if what in ('selected', 'service'):
            # Явный выбор строк для исправления — по умолчанию переводим их заново.
            self.opts.retranslate.setChecked(True)
        # Замена машинного перевода: иначе память подставит тот же машинный перевод.
        self.scope.currentIndexChanged.connect(
            lambda *_: self.opts.retranslate.setChecked(True) if self.scope.currentData() == 'service' else None)
        v.addWidget(self.opts)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr(s) for s in ('Ключ', 'Исходник', 'Текущий перевод', 'Что будет')])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 200)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.table, 3)
        self.progress = QProgressBar()
        self.progress.setFormat(tr('Переведено %v из %m'))
        self.progress.hide()
        v.addWidget(self.progress)
        self.results = []      # ChangePreview черновика, когда таблица показывает результат
        self._run_keys = []    # строки текущего запуска — для живого заполнения таблицы
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        self.log.setPlaceholderText(tr('Здесь появится ход перевода.'))
        v.addWidget(self.log, 1)

        btns = QHBoxLayout()
        self.btn_go = QPushButton(tr('Запустить'))
        self.btn_go.setProperty('accent', 'true')
        self.btn_go.clicked.connect(self.start)
        btns.addWidget(self.btn_go)
        self.test_button = QPushButton(tr('Перевести пробные 10 строк'))
        self.test_button.clicked.connect(lambda: self.start(sample=True))
        btns.addWidget(self.test_button)
        self.btn_stop = QPushButton(tr('Остановить'))
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)
        btns.addWidget(self.btn_stop)
        self.apply_button = QPushButton(tr('Применить отмеченное'))
        self.apply_button.setProperty('accent', 'true')
        self.apply_button.setToolTip(tr('Отмеченные строки станут действующим переводом в программе. '
                                        'Игровые файлы меняются отдельно — кнопкой «Записать перевод в игру».'))
        self.apply_button.clicked.connect(self.apply_checked)
        self.apply_button.hide()
        btns.addWidget(self.apply_button)
        self.check_all_button = QPushButton(tr('Отметить все'))
        self.check_all_button.setToolTip(tr('Отметить и замены уже существующего перевода.'))
        self.check_all_button.clicked.connect(self.check_all)
        self.check_all_button.hide()
        btns.addWidget(self.check_all_button)
        self.review_button = QPushButton(tr('Подробный просмотр…'))
        self.review_button.setToolTip(tr('Отдельное окно с поиском и полными текстами длинных строк.'))
        self.review_button.clicked.connect(self.review)
        self.review_button.setEnabled(bool(job_id))
        btns.addWidget(self.review_button)
        self.discard_button = QPushButton(tr('Отменить задание'))
        self.discard_button.clicked.connect(self.discard)
        self.discard_button.setEnabled(bool(job_id))
        btns.addWidget(self.discard_button)
        btns.addStretch(1)
        close = QPushButton(tr('Закрыть'))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        v.addLayout(btns)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self.update_preview)
        self.scope.currentIndexChanged.connect(self._schedule_preview)
        self.opts.changed.connect(self._schedule_preview)
        self.finished.connect(self.cleanup)
        self._warmup = None
        self.update_preview()

    # ---------- предпросмотр ----------

    def _schedule_preview(self, *_):
        self._debounce.start()

    def options(self):
        return self.opts.options()

    def _vanilla_ready(self) -> bool:
        from ck3loc.core.pipeline import vanilla_lookup_ready
        if not self.opts.needs_vanilla():
            return True
        pair = (self.ctx.project['source_lang'], self.ctx.project['target_lang'])
        if vanilla_lookup_ready(*pair):
            return True
        if self._warmup is None:
            self._warmup = VanillaWarmup(*pair, parent=self)
            self._warmup.finished.connect(self.update_preview)
            self._warmup.start()
        return False

    def _set_headers(self, last: str) -> None:
        self.table.setHorizontalHeaderLabels([tr(s) for s in ('Ключ', 'Исходник', 'Текущий перевод', last)])

    def _show_results_mode(self, on: bool) -> None:
        self.apply_button.setVisible(on)
        self.check_all_button.setVisible(on)
        if not on:
            self.results = []

    def update_preview(self, *_):
        from ck3loc.core.ops import rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, plan_translation
        if self.worker is not None and self.worker.isRunning():
            return  # во время перевода таблица показывает ход перевода
        self._show_results_mode(False)
        self._set_headers('Что будет')
        if self.ctx is None:
            self.summary.setText(tr('Мод больше не установлен. Переводы сохранены в базе.'))
            self.btn_go.setEnabled(False)
            self.test_button.setEnabled(False)
            return
        if self.job_id:
            self.rows = [{'key': r['key'], 'source': r['source_text'], 'current_target': ''}
                         for r in self.conn.execute('SELECT * FROM job_results WHERE job_id=? AND target_text IS NULL '
                                                    'AND applied=0', (self.job_id,))]
        else:
            self.rows = rows_to_translate(self.ctx, self.scope.currentData(), self.keys)
        running = self.worker is not None and self.worker.isRunning()
        if not self._vanilla_ready():
            self.summary.setText(tr('Готовлю предпросмотр: читаю ванильную локализацию CK3…'))
            self.btn_go.setEnabled(False)
            self.test_button.setEnabled(False)
            return
        name = self.opts.provider()
        pair = (self.ctx.project['source_lang'], self.ctx.project['target_lang'])
        vanilla = build_vanilla_lookup(*pair) if self.opts.needs_vanilla() else {}
        self.planned = plan_translation(self.ctx, self.rows, name, vanilla_lookup=vanilla, **self.options())
        title = tr(PROVIDERS[name].info.title)
        reused = sum(bool(r['reuse']) for r in self.planned)
        to_send = len(self.planned) - reused
        size = self.opts.batch_size()
        requests = (to_send + size - 1) // size
        model = self.opts.model_name()
        lines = [tr_format('Строк: {n}; подставится из ванили и памяти: {reused}; уйдёт переводчику: {sent} '
                           '({requests} запросов по {size} строк).',
                           n=len(self.planned), reused=reused, sent=to_send, requests=requests, size=size)
                 + (' ' + tr_format('Одновременно: {workers}, пауза между запросами: {pause} с.',
                                    workers=self.opts.max_workers(), pause=round(self.opts.pause.value(), 1))
                    if requests > 1 and (self.opts.max_workers() > 1 or self.opts.pause.value() > 0) else ''),
                 tr_format('Переводчик: {provider}', provider=title) + (f' · {model}' if model else '') + '. '
                 + tr('Стоимость неизвестна. Результаты сохраняются в черновик и ничего не меняют до применения.')]
        self.summary.setText('\n'.join(lines))
        shown = self.planned[:PREVIEW_LIMIT]
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(shown))
        for i, row in enumerate(shown):
            for j, text in enumerate((row['key'], row['source'], row.get('current_target', ''),
                                      reuse_label(row, title))):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(i, j, item)
        self.table.setUpdatesEnabled(True)
        if len(self.planned) > PREVIEW_LIMIT:
            self.summary.setText(self.summary.text() + '\n' + tr_format(
                'В таблице показаны первые {shown} строк из {total}.', shown=PREVIEW_LIMIT, total=len(self.planned)))
        self.btn_go.setEnabled(bool(self.rows) and not running)
        self.test_button.setEnabled(bool(self.rows) and not running)

    # ---------- запуск ----------

    def start(self, _checked=False, *, sample=False):
        from ck3loc.core.jobs import create_job
        name = self.opts.provider()
        if not check_key(self, name) or not self.rows:
            return
        settings.set_value('provider', name)
        rows = self.rows[:10] if sample else self.rows
        if self.job_id is None:
            self.job_id = create_job(self.ctx, rows, name, options=self.options())
        self._set_running(True)
        self.progress.show()
        self.progress.setValue(0)
        self.worker = TranslateWorker(self.mod_id, name, self.scope.currentData(),
            self.ctx.project['source_lang'], self.ctx.project['target_lang'], keys=self.keys,
            options=self.options(), job_id=self.job_id, mod_dir=self.ctx.scan.mod_dir, rows=rows)
        self.worker.progress.connect(self._on_progress)
        self.worker.line.connect(self.log.appendPlainText)
        self._show_run(rows)
        self.worker.done.connect(self._on_done)
        self.worker.finished.connect(self._worker_finished)
        self.log.appendPlainText(tr_format('Запущено: {n} строк. Можно остановить в любой момент — готовые ответы сохранятся.',
                                           n=len(rows)))
        self.worker.start()

    def _set_running(self, running: bool) -> None:
        self.btn_go.setEnabled(not running)
        self.test_button.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.review_button.setEnabled(not running and bool(self.job_id))
        self.discard_button.setEnabled(not running and bool(self.job_id))
        self.scope.setEnabled(not running and not self.job_id)
        self.opts.set_enabled(not running)

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            self.log.appendPlainText(tr('Ожидаю завершения текущего запроса. Завершённые черновики сохранены.'))

    # ---------- ход перевода и результат в этом же окне ----------

    def _show_run(self, rows) -> None:
        """Строки запуска в таблице: «Новый перевод» заполняется по мере ответов."""
        self._show_results_mode(False)
        self._set_headers('Новый перевод')
        self._run_keys = [r['key'] for r in rows[:PREVIEW_LIMIT]]
        self.table.setRowCount(len(self._run_keys))
        for i, row in enumerate(rows[:PREVIEW_LIMIT]):
            for j, text in enumerate((row['key'], row['source'], row.get('current_target', ''), tr('ожидает…'))):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(i, j, item)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        if not self.job_id or not self._run_keys:
            return
        drafts = {r['key']: r['target_text'] for r in self.conn.execute(
            'SELECT key,target_text FROM job_results WHERE job_id=? AND target_text IS NOT NULL', (self.job_id,))}
        for i, key in enumerate(self._run_keys):
            if key in drafts and self.table.item(i, 3) is not None:
                self.table.item(i, 3).setText(drafts[key])
                self.table.item(i, 3).setToolTip(drafts[key])

    def show_results(self) -> None:
        """Черновик задания в таблице: галочки и «Применить отмеченное» прямо здесь."""
        from ck3loc.core.jobs import preview_job
        from ck3loc.core.ops import load_project_context
        if not self.job_id or self.ctx is None:
            return
        self.ctx = load_project_context(self.conn, self.mod_id, self.ctx.project['source_lang'],
                                        self.ctx.project['target_lang'], mod_dir=self.ctx.scan.mod_dir)
        self.results = [r for r in preview_job(self.ctx, self.job_id) if r.after or r.change == 'blocked']
        self._set_headers('Новый перевод')
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self.results))
        states = {'add': 'добавится', 'replace': 'заменит текущий', 'unchanged': 'без изменений',
                  'blocked': 'исходник изменился'}
        for i, row in enumerate(self.results):
            key = QTableWidgetItem(row.key)
            key.setToolTip(f"{row.key}\n{tr(states.get(row.change, row.change))}")
            if row.change in ('add', 'replace'):
                key.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                # Добавления отмечены сразу; замену готового перевода отмечаете вы.
                key.setCheckState(Qt.CheckState.Checked if row.change == 'add' else Qt.CheckState.Unchecked)
            else:
                key.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 0, key)
            for j, text in enumerate((row.source, row.before, row.after), 1):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(i, j, item)
        self.table.setUpdatesEnabled(True)
        self._show_results_mode(bool(self.results))
        replaces = sum(r.change == 'replace' for r in self.results)
        self.summary.setText(tr_format('Результат: {n} строк. Отмеченные станут переводом после «Применить отмеченное»; '
                                       'замены готового перевода ({replaces}) отмечаете вы.',
                                       n=len(self.results), replaces=replaces))

    def checked_keys(self) -> set[str]:
        return {r.key for i, r in enumerate(self.results)
                if self.table.item(i, 0) and self.table.item(i, 0).checkState() == Qt.CheckState.Checked}

    def check_all(self) -> None:
        for i, row in enumerate(self.results):
            if row.change in ('add', 'replace'):
                self.table.item(i, 0).setCheckState(Qt.CheckState.Checked)

    def apply_checked(self) -> None:
        from ck3loc.core.jobs import apply_job
        keys = self.checked_keys()
        if not keys:
            QMessageBox.information(self, tr('Применить'), tr('Отметьте строки, которые нужно применить.'))
            return
        result = apply_job(self.ctx, self.job_id, keys)
        self.log.appendPlainText(tr_format('Применено строк: {n}; конфликтов: {conflicts}. Игровые файлы обновляются кнопкой «Записать перевод в игру».',
                                           n=len(result.changed), conflicts=len(result.conflicts)))
        self.show_results()

    def _on_done(self, stats):
        self.stats = stats
        if stats:
            self.job_id = stats.job_id
            self.log.appendPlainText(tr_format('{state}: готово строк {n}; ошибок {errors}. Результат — в таблице выше: '
                                               'отметьте строки и нажмите «Применить отмеченное».',
                                               state=tr(stats.state), n=stats.translated, errors=len(stats.failed)))
            for key, reason in stats.failed[:20]:
                self.log.appendPlainText(f'  {key}: {tr(reason)}')
        self._set_running(False)
        if self.job_id:
            self.show_results()
            # Разблокировка настроек запланировала пересчёт сметы — он затёр бы результат.
            self._debounce.stop()
        else:
            self.update_preview()

    def review(self):
        from ck3loc.core.jobs import apply_job, preview_job
        from ck3loc.core.ops import load_project_context
        from ck3loc.desktop.review_dialog import ReviewDialog
        if not self.job_id:
            return
        self.ctx = load_project_context(self.conn, self.mod_id, self.ctx.project['source_lang'],
            self.ctx.project['target_lang'], mod_dir=self.ctx.scan.mod_dir)
        dialog = ReviewDialog(preview_job(self.ctx, self.job_id), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = apply_job(self.ctx, self.job_id, dialog.selected_keys())
            self.log.appendPlainText(tr_format('Применено строк: {n}; конфликтов: {conflicts}. Игровые файлы обновляются кнопкой «Записать перевод в игру».',
                                               n=len(result.changed), conflicts=len(result.conflicts)))
        self.show_results()

    def discard(self):
        from ck3loc.core.jobs import discard_job
        if QMessageBox.question(self, tr('Отменить задание'), tr('Удалить неприменённые черновики? Использованный лимит или оплата не возвращается.')) == QMessageBox.StandardButton.Yes:
            discard_job(self.conn, self.job_id)
            self.job_id = None
            self._set_running(False)
            self.update_preview()

    # ---------- закрытие ----------

    def done(self, result):
        if self.worker and self.worker.isRunning() and not self._background:
            box = QMessageBox(self)
            box.setWindowTitle(tr('Задание выполняется'))
            box.setText(tr('Перевод ещё идёт. Завершённые ответы уже сохранены в черновике.'))
            background = box.addButton(tr('Продолжить в фоне'), QMessageBox.ButtonRole.AcceptRole)
            stop = box.addButton(tr('Остановить и сохранить черновик'), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(tr('Вернуться'), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is background:
                # Окно скрывается, worker и соединение живут до конца задания.
                self._background = True
                _BACKGROUND.add(self)
                super().done(result)
            elif box.clickedButton() is stop:
                self._close_after_stop = result
                self.stop()
            return
        super().done(result)

    def _worker_finished(self):
        if self._background:
            _BACKGROUND.discard(self)
            stats = self.stats
            text = tr_format('Фоновый перевод завершён: {state}; готово строк: {n}. Проверьте результат в «Истории действий».',
                             state=tr(stats.state) if stats else tr('failed'),
                             n=stats.translated if stats else 0)
            notify(text)
            self.conn.close()
            self.deleteLater()
            return
        if hasattr(self, "_close_after_stop"):
            super().done(self._close_after_stop)

    def cleanup(self, *_):
        if self._background:
            return
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        if self._warmup is not None and self._warmup.isRunning():
            self._warmup.wait()
        self.conn.close()


# Скрытые окна с идущим фоновым переводом (держим ссылки до завершения).
_BACKGROUND: set = set()


def background_workers() -> list:
    return [d.worker for d in _BACKGROUND if d.worker and d.worker.isRunning()]


def notify(text: str) -> None:
    from PySide6.QtWidgets import QApplication
    for widget in QApplication.topLevelWidgets():
        if hasattr(widget, 'add_note'):
            widget.add_note(text)
            return


# The batch wizard shares the same per-project preview/apply sequence.
from ck3loc.desktop.batch_dialog import BatchDialog  # noqa: E402
