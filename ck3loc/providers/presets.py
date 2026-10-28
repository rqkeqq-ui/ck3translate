"""Готовые адреса OpenAI-совместимых сервисов для «LLM (OpenAI-совместимый API)».

Пресет только заполняет адрес и модель в Настройках; ключ хранится один на
переводчик «openai» в системном keyring.
"""

from __future__ import annotations

from dataclasses import dataclass

from ck3loc.core import settings


@dataclass(frozen=True)
class LlmPreset:
    id: str
    title: str
    base_url: str
    model: str          # модель по умолчанию; пусто — выбрать через «Загрузить модели»
    needs_key: bool
    key_url: str = ''


PRESETS: tuple[LlmPreset, ...] = (
    LlmPreset('custom', 'Свой адрес', '', '', True),
    LlmPreset('openai', 'OpenAI', 'https://api.openai.com/v1', 'gpt-4o-mini', True,
              'https://platform.openai.com/api-keys'),
    LlmPreset('deepseek', 'DeepSeek', 'https://api.deepseek.com/v1', 'deepseek-chat', True,
              'https://platform.deepseek.com/api_keys'),
    LlmPreset('mistral', 'Mistral', 'https://api.mistral.ai/v1', 'mistral-small-latest', True,
              'https://console.mistral.ai/api-keys'),
    LlmPreset('openrouter', 'OpenRouter', 'https://openrouter.ai/api/v1', '', True, 'https://openrouter.ai/keys'),
    LlmPreset('lmstudio', 'LM Studio (локально)', 'http://127.0.0.1:1234/v1', '', False),
    LlmPreset('ollama', 'Ollama (локально)', 'http://127.0.0.1:11434/v1', '', False),
    LlmPreset('llamacpp', 'llama.cpp (локально)', 'http://127.0.0.1:8080/v1', '', False),
)
_BY_ID = {p.id: p for p in PRESETS}


def _normalize(url: str) -> str:
    return (url or '').strip().rstrip('/').lower()


def preset(preset_id: str) -> LlmPreset:
    return _BY_ID.get(preset_id, PRESETS[0])


def preset_for_url(url: str) -> str:
    target = _normalize(url)
    if not target:
        return 'custom'
    return next((p.id for p in PRESETS if p.base_url and _normalize(p.base_url) == target), 'custom')


def apply_preset(preset_id: str) -> LlmPreset:
    """Записать адрес и модель пресета; модель пользователя (не из пресетов) сохраняется."""
    chosen = preset(preset_id)
    if chosen.id == 'custom':
        return chosen
    current_model = (settings.get('openai_model') or '').strip()
    default_models = {p.model for p in PRESETS if p.model}
    values = {'openai_base_url': chosen.base_url}
    if not current_model or current_model in default_models:
        values['openai_model'] = chosen.model
    settings.save(values)
    return chosen
