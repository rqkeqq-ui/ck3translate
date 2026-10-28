"""Official Sign in with ChatGPT public-client OAuth and streamed Responses.

Contract: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
Tokens are stored only through a protected OS keyring; settings hold labels.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from ck3loc.core import net, settings
from ck3loc.core.db import data_dir
from .base import ProviderInfo, ProviderPaused, TranslationProvider

ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
KEYRING_SERVICE = 'ck3loc-chatgpt'
USAGE_URL = 'https://chatgpt.com/#settings/Usage'
BLOCKED_DIRECT = ('OpenAI refused the connection (403). The request went directly, without a proxy: the Windows '
                  'system proxy is turned off. Turn on your VPN client\'s system proxy (or TUN mode) and sign in again.')
BLOCKED_VIA_PROXY = ('OpenAI refused the connection (403) even through the Windows system proxy. Check that your '
                     'VPN or proxy route allows auth.openai.com, then sign in again.')
# Путь loopback-перенаправления по документации Sign in with ChatGPT:
# http://127.0.0.1:<port>/auth/callback, меняться может только порт.
CALLBACK_PATH = '/auth/callback'
_LOCK = threading.RLock()


def diagnose(stage: str, exc: BaseException) -> None:
    """Записать настоящую причину сбоя (без токенов и кодов) в chatgpt.log."""
    import traceback
    try:
        detail = ''.join(traceback.format_exception_only(type(exc), exc)).strip()
        cause = exc.__cause__
        if cause is not None:
            detail += ' | cause: ' + ''.join(traceback.format_exception_only(type(cause), cause)).strip()
        # Какой прокси использован и кто отказал: Cloudflare-проверка или OpenAI.
        detail += f' | proxy: {net.proxy_for(ISSUER) or "direct"}'
        response = getattr(exc, 'response', None) or getattr(cause, 'response', None)
        if response is not None:
            import re
            text = re.sub(r'<(style|script).*?</\1>', ' ', response.text[:20000], flags=re.S | re.I)
            text = ' '.join(re.sub(r'<[^>]+>', ' ', text).split())[:200]
            detail += (f' | server: {response.headers.get("server", "")}'
                       f' cf-ray: {response.headers.get("cf-ray", "")}'
                       f' cf-mitigated: {response.headers.get("cf-mitigated", "")} text: {text!r}')
        with (data_dir() / 'chatgpt.log').open('a', encoding='utf-8') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {stage}: {detail}\n")
    except OSError:
        pass


def server_error(response) -> str:
    """Краткая безопасная причина отказа сервера: статус, error/code, описание (без тела с токенами)."""
    try:
        body = response.json()
    except ValueError:
        return f'HTTP {response.status_code}'
    error = body.get('error') if isinstance(body, dict) else None
    if isinstance(error, dict):
        code, text = error.get('code') or error.get('type') or '', error.get('message') or ''
        param = error.get('param') or ''
    elif isinstance(body, dict):
        code, text, param = error or '', body.get('error_description') or '', body.get('error_reason') or ''
    else:
        code, text, param = '', '', ''
    parts = [f'HTTP {response.status_code}'] + [str(p)[:300] for p in (code, text, param) if p]
    return ': '.join(parts[:2]) + (' — ' + ' | '.join(parts[2:]) if parts[2:] else '')


def log_line(stage: str, detail: str) -> None:
    try:
        with (data_dir() / 'chatgpt.log').open('a', encoding='utf-8') as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {stage}: {detail}"
                      f" | proxy: {net.proxy_for(ISSUER) or 'direct'}\n")
    except OSError:
        pass


def protected_keyring():
    import keyring
    backend = keyring.get_keyring()
    name = type(backend).__module__ + '.' + type(backend).__name__
    # Fail closed; do not accept third-party plaintext or null backends.
    if not name.startswith(('keyring.backends.Windows.', 'keyring.backends.macOS.',
                            'keyring.backends.SecretService.', 'keyring.backends.kwallet.')):
        raise ProviderPaused('Protected OS credential storage is unavailable')
    return keyring


@contextmanager
def registration_lock(registration: str):
    from filelock import FileLock, Timeout
    path = data_dir() / ('chatgpt-' + hashlib.sha256(registration.encode()).hexdigest() + '.lock')
    try:
        with _LOCK, FileLock(str(path), timeout=30):
            yield
    except Timeout as exc:
        raise ProviderPaused('ChatGPT session is busy; retry later') from exc


def accounts() -> list[dict]:
    return list(settings.get('chatgpt_accounts') or [])


def use_account(registration: str) -> None:
    if not any(a['client_id'] == registration for a in accounts()):
        raise ProviderPaused('Unknown ChatGPT account registration')
    settings.set_value('chatgpt_account', registration)
    settings.set_value('chatgpt_model', '')


def selected_account(registration: str = '') -> dict:
    registration = registration or settings.get('chatgpt_account') or ''
    for a in accounts():
        if a['client_id'] == registration:
            return a
    raise ProviderPaused('Sign in with ChatGPT first')


def read_tokens(registration: str) -> dict:
    try:
        return json.loads(protected_keyring().get_password(KEYRING_SERVICE, registration) or '{}')
    except ProviderPaused:
        raise
    except Exception as exc:
        raise ProviderPaused('Cannot read protected ChatGPT credentials') from exc


def is_signed_in(registration: str = '') -> bool:
    """Есть ли сохранённый вход (без сети; срок токена продлевается при запросе)."""
    try:
        account = selected_account(registration)
        tokens = read_tokens(account['client_id'])
    except ProviderPaused:
        return False
    return bool(tokens.get('access_token') or tokens.get('refresh_token'))


def save_tokens(registration: str, tokens: dict) -> None:
    try:
        protected_keyring().set_password(KEYRING_SERVICE, registration, json.dumps(tokens))
    except ProviderPaused:
        raise
    except Exception as exc:
        raise ProviderPaused('Cannot save ChatGPT credentials securely') from exc


def discovery(client) -> dict:
    response = client.get(ISSUER + '/.well-known/openid-configuration')
    response.raise_for_status()
    config = response.json()
    if config.get('issuer') != ISSUER:
        raise ProviderPaused('Unexpected OpenID issuer')
    for field in ('authorization_endpoint', 'token_endpoint', 'jwks_uri', 'revocation_endpoint'):
        url = urlsplit(config.get(field, ''))
        if url.scheme != 'https' or url.netloc != 'auth.openai.com':
            raise ProviderPaused('Unexpected OpenID endpoint')
    return config


def verify_identity(client, config: dict, token: str, client_id: str, nonce: str | None = None) -> dict:
    import jwt
    try:
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256':
            raise ValueError('Unsupported signing algorithm')
        response = client.get(config['jwks_uri'])
        response.raise_for_status()
        keys = response.json()['keys']
        key = next(k for k in keys if k.get('kid') == header.get('kid'))
        claims = jwt.decode(token, jwt.PyJWK.from_dict(key).key, algorithms=['RS256'],
                            audience=client_id, issuer=ISSUER,
                            options={'require': ['sub', 'iss', 'aud', 'exp', 'iat']})
        if nonce is not None and not secrets.compare_digest(str(claims.get('nonce', '')), nonce):
            raise ValueError('Nonce mismatch')
        return claims
    except Exception as exc:
        raise ProviderPaused('ChatGPT identity validation failed') from exc


def validate_callback(params: dict, state: str, issued_id: str = '') -> tuple[str, str]:
    if not secrets.compare_digest(params.get('state', ''), state):
        raise ProviderPaused('OAuth state mismatch')
    if params.get('error'):
        raise ProviderPaused('ChatGPT sign-in was declined or failed')
    client_id = params.get('client_id') or issued_id
    if not client_id or client_id == 'dynamic_agent_client' or (issued_id and issued_id != client_id):
        raise ProviderPaused('Invalid ChatGPT client registration')
    if not params.get('code'):
        raise ProviderPaused('Missing OAuth authorization code')
    return client_id, params['code']


def login(registration: str = '', *, cancellation=None, timeout: float = 300) -> dict:
    protected_keyring()
    # Выданный при регистрации client_id, обмен кода которого не завершился,
    # используется повторно, а не регистрируется новый клиент.
    registration = registration or settings.get('chatgpt_pending_client') or ''
    account = next((a for a in accounts() if a['client_id'] == registration), None) if registration else None
    old = read_tokens(registration) if account else {}
    with registration_lock('host'):
        host_id = settings.get('chatgpt_host_id')
        if not host_id:
            host_id = 'urn:uuid:' + str(uuid.uuid4())
            settings.set_value('chatgpt_host_id', host_id)
    state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    returned = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log callback URLs or codes.

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path != CALLBACK_PATH:
                self.send_error(404)
                return
            values = parse_qs(url.query)
            if any(len(v) != 1 for v in values.values()):
                self.send_error(400)
                return
            params = {k: v[0] for k, v in values.items()}
            if not secrets.compare_digest(params.get('state', ''), state):
                self.send_error(400)
                return
            returned.update(params)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'Return to CK3 Localization Manager.')

    server = HTTPServer(('127.0.0.1', 0), Callback)
    server.timeout = 0.25
    redirect = f'http://127.0.0.1:{server.server_port}{CALLBACK_PATH}'
    try:
        with net.client(ISSUER, timeout=30) as client:
            config = discovery(client)
            # ext_agent_host_id не отправляем: официальный devkit шлёт его только для
            # совместимых развёртываний (sendHostId=false), с ним обмен кода давал invalid_grant.
            query = dict(client_id=registration or 'dynamic_agent_client',
                         response_type='code', redirect_uri=redirect, scope=SCOPES, resource=RESOURCE,
                         state=state, nonce=nonce, code_challenge_method='S256', code_challenge=challenge)
            if account:
                if old.get('id_token'):
                    query['id_token_hint'] = old['id_token']
                if account.get('email'):
                    query['login_hint'] = account['email']
            elif not registration:
                query['agent_name_hint'] = 'CK3 Localization Manager'
            if not webbrowser.open(config['authorization_endpoint'] + '?' + urlencode(query)):
                raise ProviderPaused('Cannot open the system browser')
            deadline = time.monotonic() + timeout
            while not returned:
                if time.monotonic() >= deadline or (cancellation and cancellation.cancelled):
                    raise ProviderPaused('ChatGPT sign-in stopped or timed out')
                server.handle_request()
            client_id, code = validate_callback(returned, state, registration)
            response = client.post(config['token_endpoint'], data=dict(grant_type='authorization_code',
                                   client_id=client_id, code=code, code_verifier=verifier,
                                   redirect_uri=redirect, resource=RESOURCE))
            if response.status_code != 200:
                reason = server_error(response)
                log_line('token', reason)
                if not account:
                    settings.set_value('chatgpt_pending_client', client_id)
                raise ProviderPaused(f'ChatGPT authorization failed ({reason}); sign in again')
            tokens = response.json()
            claims = verify_identity(client, config, tokens.get('id_token', ''), client_id, nonce)
            if account and claims['sub'] != account['sub']:
                raise ProviderPaused('Sign-in returned another account')
            tokens['expires_at'] = time.time() + int(tokens.get('expires_in', 0))
            enabled = 'chatgpt.tokens.use.direct' in tokens.get('scope', '').split()
            record = dict(client_id=client_id, sub=claims['sub'], email=claims.get('email', ''),
                          label=f"{claims.get('email', claims['sub'])} · {client_id[-8:]}", enabled=enabled)
            with registration_lock(client_id):
                save_tokens(client_id, tokens)
                rows = [a for a in accounts() if a['client_id'] != client_id]
                settings.save({'chatgpt_accounts': rows + [record], 'chatgpt_account': client_id,
                               'chatgpt_model': '', 'chatgpt_pending_client': ''})
            return record
    except httpx.HTTPError as exc:
        diagnose('login', exc)
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403:
            route = net.proxy_for(ISSUER)
            raise ProviderPaused(BLOCKED_VIA_PROXY if route else BLOCKED_DIRECT) from exc
        raise ProviderPaused('ChatGPT connection failed; sign in again') from exc
    except ProviderPaused as exc:
        diagnose('login', exc)
        raise
    finally:
        server.server_close()


def access_token(registration: str = '') -> str:
    account = selected_account(registration)
    registration = account['client_id']
    with registration_lock(registration):
        tokens = read_tokens(registration)
        if not tokens.get('access_token'):
            raise ProviderPaused('ChatGPT session is signed out')
        if tokens.get('expires_at', 0) <= time.time() + 60:
            if not tokens.get('refresh_token'):
                raise ProviderPaused('ChatGPT sign-in is required')
            try:
                with net.client(ISSUER, timeout=30) as client:
                    config = discovery(client)
                    response = client.post(config['token_endpoint'], data=dict(grant_type='refresh_token',
                        client_id=registration, refresh_token=tokens['refresh_token'], resource=RESOURCE))
                    if response.status_code != 200:
                        reason = server_error(response)
                        log_line('refresh', reason)
                        raise ProviderPaused(f'ChatGPT session renewal failed ({reason})')
                    replacement = response.json()
                    if replacement.get('id_token'):
                        claims = verify_identity(client, config, replacement['id_token'], registration)
                        if claims['sub'] != account['sub']:
                            raise ProviderPaused('Renewal returned another account')
                    tokens.update(replacement)
                    tokens['expires_at'] = time.time() + int(replacement.get('expires_in', 0))
                    save_tokens(registration, tokens)
            except httpx.HTTPError as exc:
                raise ProviderPaused('ChatGPT session renewal connection failed') from exc
        if 'chatgpt.tokens.use.direct' not in tokens.get('scope', '').split():
            raise ProviderPaused('ChatGPT plan usage is not authorized')
        return tokens['access_token']


def logout(registration: str = '') -> bool:
    account = selected_account(registration)
    registration = account['client_id']
    confirmed = False
    with registration_lock(registration):
        tokens = read_tokens(registration)
        try:
            if tokens.get('refresh_token'):
                with net.client(ISSUER, timeout=30) as client:
                    config = discovery(client)
                    response = client.post(config['revocation_endpoint'], data=dict(token=tokens['refresh_token'],
                        token_type_hint='refresh_token', client_id=registration))
                    confirmed = response.status_code == 200
        except httpx.HTTPError:
            pass
        finally:
            save_tokens(registration, {})
    return confirmed


def models(registration: str = '') -> list[dict]:
    try:
        with net.client(ISSUER, timeout=30) as client:
            response = client.get(RESOURCE + '/models', headers={'Authorization': 'Bearer ' + access_token(registration)})
            if response.status_code != 200:
                reason = server_error(response)
                log_line('models', reason)
                raise ProviderPaused(f'ChatGPT models unavailable ({reason})')
            return [m for m in response.json().get('models', []) if m.get('visibility') == 'list']
    except httpx.HTTPError as exc:
        raise ProviderPaused('ChatGPT model connection failed') from exc


class ChatGPTProvider(TranslationProvider):
    info = ProviderInfo('chatgpt', 'ChatGPT · подписка', needs_key=False, wave=2)
    batch_size = 250

    def __init__(self, api_key='', **options):
        super().__init__('', **options)
        self.registration = options.get('account') or settings.get('chatgpt_account') or ''
        self.model = options.get('model') or settings.get('chatgpt_model') or ''
        self.options['model'] = self.model
        self.cancellation = None

    def translate_batch(self, texts, source_lang, target_lang, glossary=None, context_types=None):
        if not self.model:
            raise ProviderPaused('Select a ChatGPT model first')
        prompt = (f'Translate CK3 localization from {source_lang} to {target_lang}. Preserve protected markers '
                  'and literal backslash-n. Return ONLY a JSON array of strings in exactly the same order.\n'
                  + json.dumps({'glossary': glossary or [], 'types': context_types or [], 'texts': texts}, ensure_ascii=False))
        completed, chunks = False, []
        try:
            with net.client(RESOURCE, timeout=httpx.Timeout(90, connect=20)) as client:
                with client.stream('POST', RESOURCE + '/responses', headers={'Authorization': 'Bearer ' + access_token(self.registration)},
                    json={'model': self.model, 'input': [{'role': 'user', 'content': prompt}], 'store': False, 'stream': True}) as response:
                    if response.status_code != 200:
                        response.read()
                        reason = server_error(response)
                        log_line('responses', reason)
                        raise ProviderPaused(f'ChatGPT paused ({reason}); check account, region or usage')
                    data_lines = []
                    for line in response.iter_lines():
                        if self.cancellation and self.cancellation.cancelled:
                            raise ProviderPaused('ChatGPT stream stopped; completed batches are preserved')
                        if line.startswith('data:'):
                            data_lines.append(line[5:].lstrip())
                        elif not line and data_lines:
                            payload = '\n'.join(data_lines)
                            data_lines = []
                            if payload == '[DONE]':
                                break
                            event = json.loads(payload)
                            kind = event.get('type', '')
                            if kind in {'response.failed', 'response.incomplete', 'error'}:
                                code = (event.get('response', {}).get('error') or event.get('error') or {}).get('code', kind)
                                raise ProviderPaused(f'ChatGPT response stopped: {code}')
                            if kind == 'response.output_text.delta':
                                chunks.append(event.get('delta', ''))
                            elif kind == 'response.completed':
                                completed = True
                                break
        except httpx.HTTPError as exc:
            raise ProviderPaused('ChatGPT stream interrupted; resume remaining rows') from exc
        if not completed:
            raise ProviderPaused('ChatGPT stream ended before response.completed')
        try:
            result = json.loads(''.join(chunks))
            if not isinstance(result, list) or len(result) != len(texts) or any(not isinstance(t, str) for t in result):
                raise ValueError('Incomplete translation array')
            return result
        except ValueError as exc:
            raise ProviderPaused('ChatGPT returned an invalid translation batch') from exc
