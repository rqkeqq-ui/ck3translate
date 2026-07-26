"""Yandex Translate (Yandex Cloud, Api-Key).

Ключ — API-ключ сервисного аккаунта Яндекс Облака; если нужен folder_id,
он передаётся в options (сохраняется в настройках).
"""

from __future__ import annotations

from .base import ProviderError, ProviderInfo, TranslationProvider, lang_code

_URL = "https://translate.api.cloud.yandex.net/translate/v2/translate"


class YandexProvider(TranslationProvider):
    info = ProviderInfo("yandex", "Yandex Translate", needs_key=True, wave=1)
    batch_size = 50

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        import httpx

        if not self.api_key:
            raise ProviderError("Не задан API-ключ Yandex. Настройки → ключи.")
        body = {
            "sourceLanguageCode": lang_code(source_lang),
            "targetLanguageCode": lang_code(target_lang),
            "texts": texts,
            "format": "PLAIN_TEXT",
        }
        folder = self.options.get("folder_id")
        if folder:
            body["folderId"] = folder
        try:
            resp = httpx.post(
                _URL,
                headers={"Authorization": f"Api-Key {self.api_key}"},
                json=body,
                timeout=60.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"Yandex Translate: HTTP {e.response.status_code} — "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"Yandex Translate: сетевая ошибка ({e})") from e
        items = payload.get("translations", [])
        if len(items) != len(texts):
            raise ProviderError("Yandex Translate вернул не все строки.")
        return [i.get("text", "") for i in items]
