"""Конвейер встроенного перевода: ваниль → память переводов → API.

Каждая строка проходит защиту игровых кодов до провайдера и валидацию
после; строки с повреждёнными кодами не сохраняются.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .bundle import key_type
from .glossary_seed import load_glossary, relevant_glossary
from .ops import ProjectContext
from .scanner import semantic_hash
from .status import MACHINE
from .store import tm_lookup_variant
from .jobs import CancellationToken, create_job, stage_result, unit_value
from ck3loc.providers.base import ProviderPaused
from .tokens import protect, restore, validate_translation
from .vanilla import load_vanilla_index


@dataclass
class TranslateStats:
    job_id: str = ''
    state: str = 'draft'
    total: int = 0
    from_vanilla: int = 0
    from_memory: int = 0
    from_api: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (key, причина)

    @property
    def translated(self) -> int:
        return self.from_vanilla + self.from_memory + self.from_api


MAX_WORKERS = 8  # одновременных запросов к переводчику
# Артикли названий титулов (*_article): в ванили ключи строчные («the »),
# в модах часто «The ». Для них — поиск без учёта регистра.
_ARTICLES = frozenset({'the', 'a', 'an'})


def vanilla_hit(lookup: dict[str, str], text: str) -> str | None:
    """Перевод из ванили CK3: точное совпадение, а для одного артикля — и без учёта регистра."""
    hit = lookup.get(text)
    if hit is None and text.strip().lower() in _ARTICLES:
        word = text.strip().lower()
        for variant in (text.lower(), word + ' ', word):
            hit = lookup.get(variant)
            if hit is not None:
                break
    return hit


def wait_pause(seconds: float, cancellation: CancellationToken) -> bool:
    """Пауза между волнами запросов; True — если за это время нажали «Остановить»."""
    deadline = time.monotonic() + seconds
    while (left := deadline - time.monotonic()) > 0:
        if cancellation.cancelled:
            return True
        time.sleep(min(0.2, left))
    return cancellation.cancelled


_VANILLA_LOCK = threading.Lock()
_VANILLA_CACHE: dict[tuple, dict[str, str]] = {}


def build_vanilla_lookup(source_lang: str, target_lang: str) -> dict[str, str]:
    """EN-текст → официальный RU-текст (через общий ключ ванили).

    Разбор ванили занимает секунды, поэтому результат кешируется на время
    работы программы (ключ включает папку игры). Словарь только читают.
    """
    from .vanilla import find_ck3_game_dir

    key = (source_lang, target_lang, str(find_ck3_game_dir() or ''))
    with _VANILLA_LOCK:
        cached = _VANILLA_CACHE.get(key)
        if cached is not None:
            return cached
        src = load_vanilla_index(source_lang)
        tgt = load_vanilla_index(target_lang)
        lookup: dict[str, str] = {}
        for _key, s_val in src.items():
            t_val = tgt.get(_key)
            if t_val and s_val.strip():
                lookup.setdefault(s_val, t_val)
        _VANILLA_CACHE[key] = lookup
        return lookup


def vanilla_lookup_ready(source_lang: str, target_lang: str) -> bool:
    from .vanilla import find_ck3_game_dir

    return (source_lang, target_lang, str(find_ck3_game_dir() or '')) in _VANILLA_CACHE


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
        elif tm_lookup_variant(ctx.conn, ctx.project["source_lang"],
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
    *, cancellation: CancellationToken | None = None,
    job_id: str | None = None, retranslate: bool = False,
    use_vanilla: bool = True, use_memory: bool = True,
    allow_service_memory: bool | None = None, rows_per_request: int | None = None,
    workers: int = 1, request_pause: float = 0.0,
) -> TranslateStats:
    """Translate into a durable draft; active units change only after Apply.

    workers — сколько запросов отправлять одновременно; request_pause — пауза
    в секундах между волнами запросов (для бесплатных тарифов с лимитом частоты).
    """
    if rows_per_request is not None and rows_per_request <= 0:
        raise ValueError('Request batch size must be positive')
    if isinstance(workers, bool) or not 1 <= int(workers) <= MAX_WORKERS:
        raise ValueError(f'Parallel requests must be between 1 and {MAX_WORKERS}')
    if request_pause is None or float(request_pause) < 0:
        raise ValueError('Pause between requests must not be negative')
    # Провайдер может ограничить параллельность (бесплатный Google — один запрос за раз).
    workers = min(int(workers), int(getattr(provider, 'max_workers', MAX_WORKERS) or MAX_WORKERS))
    request_pause = float(request_pause)
    cancellation = cancellation or CancellationToken()
    stats = TranslateStats(total=len(rows))
    source_lang = ctx.project["source_lang"]
    target_lang = ctx.project["target_lang"]
    mod_id = ctx.project["mod_id"]
    vl = vanilla_lookup if vanilla_lookup is not None else build_vanilla_lookup(
        source_lang, target_lang
    )
    glossary = load_glossary(ctx.conn, mod_id, source_lang, target_lang)
    model = provider.options.get('model', '') if hasattr(provider, 'options') else ''
    options = dict(retranslate=retranslate, use_vanilla=use_vanilla, use_memory=use_memory,
                   allow_service_memory=allow_service_memory, rows_per_request=rows_per_request,
                   workers=workers, request_pause=request_pause)
    if job_id is None:
        job_id = create_job(ctx, rows, provider.info.name, model, options)
    job = ctx.conn.execute('SELECT * FROM translation_jobs WHERE id=?', (job_id,)).fetchone()
    if not job or job['project_id'] != ctx.project_id or job['state'] == 'discarded':
        raise ValueError('Invalid or discarded translation job')
    stats.job_id = job_id
    options['account'] = getattr(provider, 'registration', '')
    from .jobs import encode
    ctx.conn.execute("UPDATE translation_jobs SET state='running',provider=?,model=?,options=? WHERE id=?",
                     (provider.info.name, model, encode(options), job_id))
    ctx.conn.commit()
    if hasattr(provider, 'cancellation'):
        provider.cancellation = cancellation
    completed = {r['key'] for r in ctx.conn.execute('SELECT * FROM job_results WHERE job_id=?', (job_id,))
                 if r['target_text'] or r['applied']}
    registered = {r['key']: r for r in ctx.conn.execute('SELECT * FROM job_results WHERE job_id=?', (job_id,))}
    if allow_service_memory is None:
        allow_service_memory = provider.info.wave != 2

    def save(key: str, target_text: str, origin: str, *, kind=None, method='direct', saved_model=''):
        stage_result(ctx.conn, job_id, key, target_text, origin, kind=kind,
                     model=saved_model, method=method)

    pending: list[dict] = []
    for row in rows:
        key, text = row["key"], row["source"]
        if cancellation.cancelled:
            break
        if key in completed:
            continue
        current_unit = ctx.conn.execute('SELECT * FROM translation_units WHERE project_id=? AND key=?',
                                        (ctx.project_id, key)).fetchone()
        if (key not in registered or registered[key]['source_text'] != text
                or ctx.source_values.get(key) != text
                or registered[key]['baseline'] != unit_value(current_unit)):
            stats.failed.append((key, 'Source changed; export or plan this key again'))
            continue
        hit = vanilla_hit(vl, text) if use_vanilla and not retranslate else None
        if hit is not None:
            try:
                save(key, hit, 'vanilla')
                stats.from_vanilla += 1
                continue
            except ValueError:
                pass
        tm_hit = (tm_lookup_variant(ctx.conn, source_lang, target_lang, text,
                                   project_id=ctx.project_id, key=key,
                                   allow_unreviewed_service=allow_service_memory)
                  if use_memory and not retranslate else None)
        if tm_hit is not None:
            try:
                save(key, tm_hit['target_text'], tm_hit['provider'], kind=tm_hit['origin_kind'],
                     method='memory', saved_model=tm_hit['model'])
                stats.from_memory += 1
                continue
            except ValueError:
                pass
        pending.append(row)
    ctx.conn.commit()

    done = stats.from_vanilla + stats.from_memory + len(completed)
    if progress_cb:
        progress_cb(done, stats.total)

    batch_size = min(rows_per_request or getattr(provider, 'batch_size', 40), getattr(provider, 'batch_size', 40))
    batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]

    def request(item):
        """Один запрос; выполняется в рабочем потоке и базу не трогает."""
        batch, protected, terms = item
        try:
            results = provider.translate_batch(
                [p.text for p in protected], source_lang, target_lang,
                glossary=terms, context_types=[key_type(r["key"]) for r in batch],
            )
            if len(results) != len(batch) or any(not isinstance(t, str) for t in results):
                raise ProviderPaused('Incomplete batch: translation count does not match request')
            return results, None
        except Exception as exc:  # noqa: BLE001 — ошибка провайдера не роняет очередь
            return None, exc

    def save_batch(batch, protected, results):
        for r, prot, translated in zip(batch, protected, results):
            target, problems = restore(translated, prot.mapping)
            if problems:
                stats.failed.append((r["key"], "; ".join(problems)))
                continue
            errors = validate_translation(r["source"], target)
            if errors:
                stats.failed.append((r["key"], "; ".join(errors)))
                continue
            try:
                save(r["key"], target, provider.info.name, saved_model=model)
            except ValueError as exc:
                stats.failed.append((r['key'], str(exc)))
                continue
            stats.from_api += 1

    # Запросы идут волнами по `workers` одновременно; ответы сохраняются здесь,
    # в потоке задания. Остановка и пауза между запросами — между волнами.
    for wave_start in range(0, len(batches), workers):
        if cancellation.cancelled:
            break
        if wave_start and request_pause and wait_pause(request_pause, cancellation):
            break
        wave = [(batch, [protect(r["source"]) for r in batch],
                 relevant_glossary(glossary, [r["source"] for r in batch]))
                for batch in batches[wave_start:wave_start + workers]]
        if len(wave) == 1:
            outcomes = [request(wave[0])]
        else:
            with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                outcomes = list(pool.map(request, wave))
        paused = False
        for (batch, protected, _terms), (results, error) in zip(wave, outcomes):
            if isinstance(error, ProviderPaused):
                stats.state = 'paused'
                stats.failed.append((batch[0]['key'], str(error)))
                paused = True
                continue
            if error is not None:
                stats.failed.extend((r["key"], str(error)) for r in batch)
            else:
                save_batch(batch, protected, results)
            done += len(batch)
            if progress_cb:
                progress_cb(done, stats.total)
        ctx.conn.commit()
        if paused:
            break
    if cancellation.cancelled:
        stats.state = 'stopped'
    elif stats.state == 'draft' and stats.failed:
        stats.state = 'failed'
    elif stats.state == 'draft':
        stats.state = 'completed'
    ctx.conn.execute('UPDATE translation_jobs SET state=? WHERE id=?', (stats.state, job_id))
    ctx.conn.commit()
    return stats


def plan_translation(ctx, rows, provider_name: str, *, retranslate=False, use_vanilla=True,
                     use_memory=True, allow_service_memory=False, vanilla_lookup=None,
                     rows_per_request=40, workers=1, request_pause=0.0) -> list[dict]:
    """Pure preview: no requests, jobs, unit changes or memory usage timestamps."""
    from .provenance import LLM_PROVIDERS
    vl = vanilla_lookup if vanilla_lookup is not None else build_vanilla_lookup(
        ctx.project['source_lang'], ctx.project['target_lang']) if use_vanilla and not retranslate else {}
    result = []
    for row in rows:
        hit = vanilla_hit(vl, row['source']) if use_vanilla and not retranslate else None
        memory = tm_lookup_variant(ctx.conn, ctx.project['source_lang'], ctx.project['target_lang'],
            row['source'], project_id=ctx.project_id, key=row['key'],
            allow_unreviewed_service=allow_service_memory or provider_name not in LLM_PROVIDERS
            ) if use_memory and not retranslate and hit is None else None
        result.append({**row, 'reuse': 'vanilla' if hit else 'memory' if memory else '',
                       'reuse_target': hit or (memory['target_text'] if memory else ''),
                       'reuse_provider': memory['provider'] if memory else 'vanilla' if hit else provider_name})
    return result
