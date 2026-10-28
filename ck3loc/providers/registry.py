"""Реестр провайдеров и хранение API-ключей (Windows Credential Manager)."""

from __future__ import annotations

from .base import ProviderError, TranslationProvider
from .deepl import DeepLProvider
from .google import GoogleProvider
from .google_free import GoogleFreeProvider
from .llm import AnthropicProvider, OpenAICompatProvider
from .yandex import YandexProvider
from .chatgpt import ChatGPTProvider

PROVIDERS: dict[str, type[TranslationProvider]] = {
    "google_free": GoogleFreeProvider,
    "google": GoogleProvider,
    "yandex": YandexProvider,
    "deepl": DeepLProvider,
    "claude": AnthropicProvider,
    "openai": OpenAICompatProvider,
    'chatgpt': ChatGPTProvider,
}

_KEYRING_SERVICE = "ck3loc"


def get_api_key(provider_name: str) -> str:
    try:
        import keyring

        return keyring.get_password(_KEYRING_SERVICE, f"{provider_name}_api_key") or ""
    except Exception:
        return ""


def set_api_key(provider_name: str, key: str) -> None:
    import keyring

    if key:
        keyring.set_password(_KEYRING_SERVICE, f"{provider_name}_api_key", key)
    else:
        try:
            keyring.delete_password(_KEYRING_SERVICE, f"{provider_name}_api_key")
        except Exception:
            pass


# Параметры провайдеров из «Настройки → Дополнительно для LLM и Яндекса».
SETTING_OPTIONS = {
    "openai": {"base_url": "openai_base_url", "model": "openai_model"},
    "claude": {"model": "claude_model"},
    "yandex": {"folder_id": "yandex_folder_id"},
}


def provider_options(name: str, options: dict | None = None) -> dict:
    """Явные параметры важнее сохранённых в настройках."""
    from ck3loc.core import settings

    merged = dict(options or {})
    for option, key in SETTING_OPTIONS.get(name, {}).items():
        if not merged.get(option):
            value = (settings.get(key) or "").strip()
            if value:
                merged[option] = value
    return merged


def key_required(name: str) -> bool:
    """Нужен ли ключ: свой OpenAI-совместимый сервер (локальный ИИ) может работать без него."""
    cls = PROVIDERS.get(name)
    if cls is None or not cls.info.needs_key:
        return False
    if name == "openai":
        return not provider_options(name).get("base_url")
    return True


def make_provider(name: str, **options) -> TranslationProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(
            f"Неизвестный провайдер «{name}». Доступны: {', '.join(PROVIDERS)}"
        )
    return cls(api_key=get_api_key(name), **provider_options(name, options))


def provider_titles() -> list[tuple[str, str, int]]:
    """(имя, заголовок, волна) — для интерфейса."""
    return [(n, c.info.title, c.info.wave) for n, c in PROVIDERS.items()]
