"""DeepL API (Free и Pro — определяется по суффиксу ключа ':fx')."""

from __future__ import annotations

from .base import ProviderError, ProviderInfo, TranslationProvider, lang_code


class DeepLProvider(TranslationProvider):
    info = ProviderInfo("deepl", "DeepL", needs_key=True, wave=1)
    batch_size = 40

    def translate_batch(self, texts, source_lang, target_lang,
                        glossary=None, context_types=None):
        import httpx

        if not self.api_key:
            raise ProviderError("Не задан API-ключ DeepL. Настройки → ключи.")
        host = ("api-free.deepl.com" if self.api_key.endswith(":fx")
                else "api.deepl.com")
        try:
            resp = httpx.post(
                f"https://{host}/v2/translate",
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                json={
                    "text": texts,
                    "source_lang": lang_code(source_lang).upper(),
                    "target_lang": lang_code(target_lang).upper(),
                    "preserve_formatting": True,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"DeepL: HTTP {e.response.status_code} — {e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"DeepL: сетевая ошибка ({e})") from e
        items = payload.get("translations", [])
        if len(items) != len(texts):
            raise ProviderError("DeepL вернул не все строки.")
        return [i.get("text", "") for i in items]
