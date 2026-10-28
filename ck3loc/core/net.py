"""HTTP-клиенты приложения с учётом системного прокси.

httpx сам читает только переменные окружения HTTP(S)_PROXY. На Windows
прокси обычно задан в настройках системы (реестр; так делают v2rayN, Clash и
корпоративные сети), и браузер им пользуется, а программа — нет. Из-за этого
сервисы, недоступные напрямую (например, вход OpenAI из части регионов),
отвечали 403, хотя в браузере всё открывалось. Здесь прокси берётся так же,
как его видит система: переменные окружения, затем настройки Windows, с учётом
исключений (localhost, локальные адреса).
"""
from __future__ import annotations

import urllib.request
from urllib.parse import urlsplit

import httpx


def proxy_for(url: str) -> str | None:
    """Адрес прокси для url или None, если идти напрямую.

    Переменные HTTP(S)_PROXY важнее настроек Windows. Важно: одна лишь
    переменная NO_PROXY (её ставят многие программы) не должна отключать
    системный прокси — urllib.getproxies() в этом случае вовсе не смотрит
    реестр, и запросы уходили напрямую.
    """
    parts = urlsplit(url)
    host = parts.hostname or ''
    scheme = parts.scheme or 'https'
    # Локальный сервер (свой ИИ на 127.0.0.1) никогда не идёт через прокси.
    if host in ('localhost', '127.0.0.1', '::1') or host.startswith('127.'):
        return None
    try:
        env = urllib.request.getproxies_environment()
        registry = (urllib.request.getproxies_registry()
                    if hasattr(urllib.request, 'getproxies_registry') else {})
    except OSError:
        return None
    # Исключения из NO_PROXY действуют при любом источнике прокси.
    if host and env.get('no') and urllib.request.proxy_bypass_environment(host, env):
        return None
    proxy = env.get(scheme) or env.get('https') or env.get('http')
    if not proxy:
        proxy = registry.get(scheme) or registry.get('https') or registry.get('http')
        try:
            if proxy and host and urllib.request.proxy_bypass_registry(host):
                return None
        except (OSError, AttributeError):
            pass
    if not proxy or not proxy.startswith(('http://', 'https://')):
        return None  # SOCKS требует отдельной библиотеки; идём напрямую
    return proxy


def client(base_url: str = 'https://api.openai.com', **kwargs) -> httpx.Client:
    """httpx.Client с системным прокси для запросов к base_url."""
    proxy = proxy_for(base_url)
    if proxy:
        kwargs.setdefault('proxy', proxy)
    return httpx.Client(**kwargs)


def post(url: str, **kwargs) -> httpx.Response:
    timeout = kwargs.pop('timeout', None)
    with client(url, timeout=timeout) as c:
        return c.post(url, **kwargs)


def get(url: str, **kwargs) -> httpx.Response:
    timeout = kwargs.pop('timeout', None)
    follow = kwargs.pop('follow_redirects', False)
    with client(url, timeout=timeout, follow_redirects=follow) as c:
        return c.get(url, **kwargs)
