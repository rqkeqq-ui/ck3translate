"""Translation origin is independent of human review and reuse method."""
from __future__ import annotations

# google_free — тот же Google Translate без ключа: для фильтров и удаления это сервис Google.
SERVICE_PROVIDERS = frozenset({'google', 'google_free', 'deepl', 'yandex'})
LLM_PROVIDERS = frozenset({'openai', 'claude', 'chatgpt', 'external_llm'})


def origin_kind(provider: str) -> str:
    if provider in SERVICE_PROVIDERS:
        return 'service'
    if provider in LLM_PROVIDERS:
        return 'llm'
    return provider if provider in {'manual', 'vanilla', 'native', 'external_mod'} else 'unknown'


def removable(unit: dict) -> bool:
    return (unit.get('origin_kind') == 'service'
            and unit.get('provider') in SERVICE_PROVIDERS
            and unit.get('status') == 'machine' and bool(unit.get('target_text')))


def counts(units: dict, keys=None) -> dict[str, int]:
    result = {}
    for key, raw in units.items():
        unit = dict(raw)
        if keys is not None and key not in keys:
            continue
        if unit.get('target_text'):
            kind = unit.get('origin_kind', 'unknown')
            result[kind] = result.get(kind, 0) + 1
            if unit.get('status') in {'reviewed', 'approved'}:
                result['reviewed'] = result.get('reviewed', 0) + 1
            if removable(unit):
                result['unreviewed_service'] = result.get('unreviewed_service', 0) + 1
    return result
