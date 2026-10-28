"""Вход в ChatGPT: одна кнопка, статус и выход; модель выбирается при переводе.

Все сетевые операции идут вне потока интерфейса. Пароль ChatGPT приложение
не видит: вход открывается в обычном браузере.
"""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from ck3loc.core import settings
from ck3loc.core.i18n import tr, tr_format
from ck3loc.core.jobs import CancellationToken
from ck3loc.desktop.widgets import Card
from ck3loc.providers import chatgpt

# Потоки входа живут дольше окна, из которого их запустили; при выходе из
# приложения главное окно отменяет их и дожидается завершения.
ACTIVE_WORKERS: set = set()


class AccountWorker(QThread):
    result = Signal(object, str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.cancellation = CancellationToken()

    def run(self):
        try:
            self.result.emit(self.operation(self.cancellation), '')
        except Exception as exc:  # noqa: BLE001
            self.result.emit(None, tr(str(exc)))


class ChatGPTAccountBar(QWidget):
    """Статус входа, «Войти через ChatGPT» / «Выйти», при необходимости — модель."""

    changed = Signal()

    def __init__(self, show_models: bool = False, parent=None):
        super().__init__(parent)
        self.show_models = show_models
        self._login_worker = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel()
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        self.account = QComboBox()
        self.account.setToolTip(tr('Аккаунт ChatGPT'))
        self.account.currentIndexChanged.connect(self._switch_account)
        row.addWidget(self.account)
        self.model = QComboBox()
        self.model.setMinimumWidth(200)
        self.model.setToolTip(tr('Модель из списка, доступного вашему аккаунту'))
        self.model.currentIndexChanged.connect(self._switch_model)
        row.addWidget(self.model)
        self.login_button = QPushButton(tr('Войти через ChatGPT'))
        self.login_button.setProperty('accent', 'true')
        self.login_button.clicked.connect(self.login)
        row.addWidget(self.login_button)
        self.cancel_button = QPushButton(tr('Отменить вход'))
        self.cancel_button.clicked.connect(self.cancel_login)
        row.addWidget(self.cancel_button)
        self.logout_button = QPushButton(tr('Выйти'))
        self.logout_button.clicked.connect(self.logout)
        row.addWidget(self.logout_button)
        self.usage_button = QPushButton(tr('Лимиты подписки'))
        self.usage_button.setFlat(True)
        self.usage_button.setToolTip(tr('Открыть настройки использования ChatGPT в браузере'))
        self.usage_button.clicked.connect(lambda: webbrowser.open(chatgpt.USAGE_URL))
        row.addWidget(self.usage_button)
        self.refresh()

    # ---------- состояние ----------

    def signed_in(self) -> bool:
        return chatgpt.is_signed_in()

    def refresh(self):
        accounts = chatgpt.accounts()
        current = settings.get('chatgpt_account') or ''
        self.account.blockSignals(True)
        self.account.clear()
        for a in accounts:
            self.account.addItem(a.get('email') or a['label'], a['client_id'])
        self.account.setCurrentIndex(max(0, self.account.findData(current)))
        self.account.blockSignals(False)
        self.account.setVisible(len(accounts) > 1)
        waiting = self._login_worker is not None
        signed = self.signed_in()
        account = next((a for a in accounts if a['client_id'] == current), None)
        if waiting:
            self.status.setText(tr('Ожидаю входа в браузере… Вернитесь в приложение после подтверждения.'))
        elif signed and account and not account.get('enabled', True):
            self.status.setText(tr('Вход выполнен, но использование плана не разрешено. Войдите снова и разрешите доступ.'))
        elif signed and account:
            self.status.setText(tr_format('Подключено: {account}', account=account.get('email') or account['label']))
        else:
            self.status.setText(tr('Не подключено. Вход откроется в браузере; пароль приложение не запрашивает.'))
        self.login_button.setVisible(not waiting and (not signed or not (account or {}).get('enabled', True)))
        self.login_button.setText(tr('Войти снова') if signed else tr('Войти через ChatGPT'))
        self.cancel_button.setVisible(waiting)
        self.logout_button.setVisible(signed and not waiting)
        self.model.setVisible(self.show_models and signed and not waiting)
        if self.show_models and signed and not waiting and self.model.count() == 0:
            self.load_models()

    def selected_model(self) -> str:
        return self.model.currentData() or settings.get('chatgpt_model') or ''

    # ---------- действия ----------

    def _run(self, operation, callback):
        worker = AccountWorker(operation)
        ACTIVE_WORKERS.add(worker)

        def done(result, error):
            try:
                callback(result, error)
            except RuntimeError:
                pass  # окно уже закрыто

        worker.result.connect(done)
        worker.finished.connect(lambda: ACTIVE_WORKERS.discard(worker))
        worker.start()
        return worker

    def login(self):
        current = settings.get('chatgpt_account') or ''
        # Известный аккаунт без действующего входа переподключаем той же регистрацией.
        registration = current if current and not self.signed_in() else ''

        def done(record, error):
            self._login_worker = None
            self.model.clear()
            self.refresh()
            if error:
                self.status.setText(error)
            self.changed.emit()

        self._login_worker = self._run(
            lambda token: chatgpt.login(registration, cancellation=token), done)
        self.refresh()

    def cancel_login(self):
        if self._login_worker is not None:
            self._login_worker.cancellation.cancel()

    def logout(self):
        registration = settings.get('chatgpt_account') or ''
        if not registration:
            return

        def done(confirmed, error):
            self.model.clear()
            self.refresh()
            if error:
                self.status.setText(error)
            elif not confirmed:
                self.status.setText(tr('Выход выполнен. Отзыв на сервере не подтверждён; '
                                       'отключите приложение в настройках ChatGPT.'))
            self.changed.emit()

        self._run(lambda token: chatgpt.logout(registration), done)

    def load_models(self):
        registration = settings.get('chatgpt_account') or ''
        self.model.clear()
        self.model.addItem(tr('Загрузка моделей…'), '')
        self.model.setEnabled(False)

        def done(models, error):
            self.model.blockSignals(True)
            self.model.clear()
            for item in models or []:
                self.model.addItem(item.get('display_name') or item['slug'], item['slug'])
            saved = settings.get('chatgpt_model')
            self.model.setCurrentIndex(max(0, self.model.findData(saved)))
            self.model.setEnabled(bool(models))
            self.model.blockSignals(False)
            if error:
                self.status.setText(error)
            elif models:
                self._switch_model()
            self.changed.emit()

        self._run(lambda token: chatgpt.models(registration), done)

    def _switch_account(self, *_):
        registration = self.account.currentData()
        if registration and registration != settings.get('chatgpt_account'):
            chatgpt.use_account(registration)
            self.model.clear()
            self.refresh()
            self.changed.emit()

    def _switch_model(self, *_):
        if self.model.currentData():
            settings.set_value('chatgpt_model', self.model.currentData())
            self.changed.emit()


class ChatGPTSettings(Card):
    def __init__(self, parent=None):
        super().__init__('ChatGPT — использовать подписку', parent=parent)
        note = QLabel(tr('Перевод по подписке ChatGPT без ключа API. Запросы расходуют лимиты вашего плана; '
                         'модель выбирается в окне перевода.'))
        note.setWordWrap(True)
        note.setProperty('role', 'dim')
        self.add(note)
        self.bar = ChatGPTAccountBar(show_models=False)
        self.add(self.bar)

    @property
    def workers(self):
        return ACTIVE_WORKERS

    def shutdown(self):
        for worker in list(ACTIVE_WORKERS):
            worker.cancellation.cancel()
            worker.wait()
