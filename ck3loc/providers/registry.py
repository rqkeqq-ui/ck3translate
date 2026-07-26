"""Реестр провайдеров и хранение API-ключей (Windows Credential Manager)."""

from __future__ import annotations

from .base import ProviderError, TranslationProvider
from .deepl import DeepLProvider
from .google import GoogleProvider
from .llm import AnthropicProvider, OpenAICompatProvider
from .yandex import YandexProvider

PROVIDERS: dict[str, type[TranslationProvider]] = {
    "google": GoogleProvider,
    "yandex": YandexProvider,
    "deepl": DeepLProvider,
    "claude": AnthropicProvider,
    "openai": OpenAICompatProvider,
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


def make_provider(name: str, **options) -> TranslationProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(
            f"Неизвестный провайдер «{name}». Доступны: {', '.join(PROVIDERS)}"
        )
    return cls(api_key=get_api_key(name), **options)


def provider_titles() -> list[tuple[str, str, int]]:
    """(имя, заголовок, волна) — для интерфейса."""
    return [(n, c.info.title, c.info.wave) for n, c in PROVIDERS.items()]
