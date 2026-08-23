"""Конвейер встроенного перевода: ваниль → память переводов → API.

Каждая строка проходит защиту игровых кодов до провайдера и валидацию
после; строки с повреждёнными кодами не сохраняются.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bundle import key_type
from .glossary_seed import load_glossary
from .ops import ProjectContext
from .scanner import semantic_hash
from .status import MACHINE
from .store import tm_lookup, tm_store, upsert_unit
from .tokens import protect, restore, validate_translation
from .vanilla import load_vanilla_index


@dataclass
class TranslateStats:
    total: int = 0
    from_vanilla: int = 0
    from_memory: int = 0
    from_api: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (key, причина)

    @property
    def translated(self) -> int:
        return self.from_vanilla + self.from_memory + self.from_api


def build_vanilla_lookup(source_lang: str, target_lang: str) -> dict[str, str]:
    """EN-текст → официальный RU-текст (через общий ключ ванили)."""
    src = load_vanilla_index(source_lang)
    tgt = load_vanilla_index(target_lang)
    lookup: dict[str, str] = {}
    for key, s_val in src.items():
        t_val = tgt.get(key)
        if t_val and s_val.strip():
            lookup.setdefault(s_val, t_val)
    return lookup


@dataclass
class EstimateResult:
    rows: int = 0
    covered_by_vanilla: int = 0
    covered_by_memory: int = 0
    chars_to_api: int = 0


def estimate(
    ctx: ProjectContext,
    rows: list[dict],
    vanilla_lookup: dict[str, str] | None = None,
) -> EstimateResult:
    """Смета до запуска: что закроется бесплатно, что пойдёт в API."""
    vl = vanilla_lookup if vanilla_lookup is not None else build_vanilla_lookup(
        ctx.project["source_lang"], ctx.project["target_lang"]
    )
    est = EstimateResult(rows=len(rows))
    for row in rows:
        text = row["source"]
        if text in vl:
            est.covered_by_vanilla += 1
        elif tm_lookup(ctx.conn, ctx.project["source_lang"],
                       ctx.project["target_lang"], text):
            est.covered_by_memory += 1
        else:
            est.chars_to_api += len(text)
    return est


def translate_rows(
    ctx: ProjectContext,
    rows: list[dict],
    provider,
    progress_cb=None,
    vanilla_lookup: dict[str, str] | None = None,
) -> TranslateStats:
    """Перевести строки [{key, source}] и сохранить в базу (статус «машинный»)."""
    stats = TranslateStats(total=len(rows))
    source_lang = ctx.project["source_lang"]
    target_lang = ctx.project["target_lang"]
    mod_id = ctx.project["mod_id"]
    vl = vanilla_lookup if vanilla_lookup is not None else build_vanilla_lookup(
        source_lang, target_lang
    )
    glossary = load_glossary(ctx.conn, mod_id, source_lang, target_lang)

    def save(key: str, source_text: str, target_text: str, origin: str):
        upsert_unit(
            ctx.conn, ctx.project_id, key, source_text,
            semantic_hash(source_text), target_text, MACHINE, origin,
        )
        if origin not in ("vanilla",):
            tm_store(ctx.conn, source_lang, target_lang, source_text,
                     target_text, mod_id, key, approved=False, provider=origin)

    pending: list[dict] = []
    for row in rows:
        key, text = row["key"], row["source"]
        hit = vl.get(text)
        if hit is not None:
            save(key, text, hit, "vanilla")
            stats.from_vanilla += 1
            continue
        tm_hit = tm_lookup(ctx.conn, source_lang, target_lang, text)
        if tm_hit is not None:
            save(key, text, tm_hit, "memory")
            stats.from_memory += 1
            continue
        pending.append(row)
    ctx.conn.commit()

    done = stats.from_vanilla + stats.from_memory
    if progress_cb:
        progress_cb(done, stats.total)

    batch_size = getattr(provider, "batch_size", 40)
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        protected = [protect(r["source"]) for r in batch]
        texts = [p.text for p in protected]
        types = [key_type(r["key"]) for r in batch]
        try:
            results = provider.translate_batch(
                texts, source_lang, target_lang,
                glossary=glossary, context_types=types,
            )
        except Exception as e:  # noqa: BLE001 — ошибка провайдера не роняет очередь
            for r in batch:
                stats.failed.append((r["key"], str(e)))
            done += len(batch)
            if progress_cb:
                progress_cb(done, stats.total)
            continue
        for r, prot, translated in zip(batch, protected, results):
            target, problems = restore(translated, prot.mapping)
            if problems:
                stats.failed.append((r["key"], "; ".join(problems)))
                continue
            errors = validate_translation(r["source"], target)
            if errors:
                stats.failed.append((r["key"], "; ".join(errors)))
                continue
            save(r["key"], r["source"], target, provider.info.name)
            stats.from_api += 1
        ctx.conn.commit()
        done += len(batch)
        if progress_cb:
            progress_cb(done, stats.total)
    return stats
