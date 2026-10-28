"""Durable drafts and conflict-aware apply/undo, shared by GUI and CLI."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field

from .provenance import origin_kind, removable
from .scanner import semantic_hash
from .store import _now, get_units, tm_store, upsert_unit
from .tokens import validate_translation


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def unit_value(unit) -> str:
    # Disk bookkeeping is allowed to change between apply and undo.
    data = dict(unit) if unit is not None else None
    if data:
        data.pop('target_hash_written', None)
    return encode(data)


def create_job(ctx, rows: list[dict], provider: str = '', model: str = '',
               options: dict | None = None) -> str:
    job_id = uuid.uuid4().hex
    units = get_units(ctx.conn, ctx.project_id)
    with ctx.conn:
        ctx.conn.execute('INSERT INTO translation_jobs VALUES (?,?,?,?,?,?,?)',
                         (job_id, ctx.project_id, 'draft', provider, model,
                          encode(options or {}), _now()))
        ctx.conn.executemany('''INSERT INTO job_results
            (job_id,key,source_text,baseline) VALUES (?,?,?,?)''',
            [(job_id, r['key'], r['source'], unit_value(units.get(r['key'])))
             for r in rows])
    return job_id


def stage_result(conn, job_id: str, key: str, target: str, provider: str,
                 *, kind: str | None = None, model: str = '', method: str = 'direct') -> None:
    row = conn.execute('SELECT source_text FROM job_results WHERE job_id=? AND key=?',
                       (job_id, key)).fetchone()
    if row is None:
        raise ValueError('Key does not belong to this job')
    problems = validate_translation(row['source_text'], target)
    if not target.strip() or problems:
        raise ValueError('; '.join(problems) or 'Empty translation')
    conn.execute('''UPDATE job_results SET target_text=?, provenance=?, error=''
        WHERE job_id=? AND key=? AND applied=0''',
        (target, encode({'provider': provider, 'origin_kind': kind or origin_kind(provider),
                         'model': model, 'method': method, 'job_id': job_id}), job_id, key))


@dataclass
class ChangePreview:
    key: str
    source: str
    before: str
    after: str
    change: str
    reason: str = ''


def preview_job(ctx, job_id: str) -> list[ChangePreview]:
    job = ctx.conn.execute('SELECT * FROM translation_jobs WHERE id=?', (job_id,)).fetchone()
    if not job or job['project_id'] != ctx.project_id:
        raise ValueError('Job belongs to another project')
    units = get_units(ctx.conn, ctx.project_id)
    current = {r.key: r.target_text or r.native_target or '' for r in ctx.rows}
    out = []
    for row in ctx.conn.execute('SELECT * FROM job_results WHERE job_id=? ORDER BY key', (job_id,)):
        before = current.get(row['key'], '')
        reason = ''
        if ctx.source_values.get(row['key']) != row['source_text']:
            reason = 'Source changed or mod is unavailable'
        elif before == row['target_text']:
            pass
        elif unit_value(units.get(row['key'])) != row['baseline']:
            reason = 'Translation changed after preview'
        elif row['applied']:
            reason = 'Already applied'
        elif not row['target_text']:
            reason = row['error'] or 'Not completed'
        change = ('blocked' if reason else 'unchanged' if before == row['target_text']
                  else 'replace' if before else 'add')
        out.append(ChangePreview(row['key'], row['source_text'], before,
                                 row['target_text'] or '', change, reason))
    return out


@dataclass
class ActionResult:
    action_id: str = ''
    changed: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)


def apply_job(ctx, job_id: str, keys: set[str] | None = None) -> ActionResult:
    preview = preview_job(ctx, job_id)
    selected = {r.key for r in preview if r.change == 'add'} if keys is None else set(keys)
    result = ActionResult(uuid.uuid4().hex)
    with ctx.conn:
        ctx.conn.execute('INSERT INTO translation_actions VALUES (?,?,?,?,0)',
                         (result.action_id, ctx.project_id, 'apply', _now()))
        for row in preview:
            if row.key not in selected or row.change == 'unchanged':
                continue
            if row.change == 'blocked':
                result.conflicts.append((row.key, row.reason))
                continue
            draft = ctx.conn.execute('SELECT * FROM job_results WHERE job_id=? AND key=?',
                                     (job_id, row.key)).fetchone()
            p = json.loads(draft['provenance'])
            upsert_unit(ctx.conn, ctx.project_id, row.key, row.source,
                        semantic_hash(row.source), row.after, 'machine', **p)
            existing = ctx.conn.execute('''SELECT id FROM translation_memory
                WHERE source_lang=? AND target_lang=? AND source_text=? AND target_text=? AND provider=? AND origin_kind=?''',
                (ctx.project['source_lang'], ctx.project['target_lang'], row.source, row.after, p['provider'], p['origin_kind'])).fetchone()
            memory_id = tm_store(ctx.conn, ctx.project['source_lang'], ctx.project['target_lang'],
                                 row.source, row.after, ctx.project['mod_id'], row.key, **p)
            after = ctx.conn.execute('SELECT * FROM translation_units WHERE project_id=? AND key=?',
                                     (ctx.project_id, row.key)).fetchone()
            ctx.conn.execute('''INSERT INTO action_rows
                (action_id,key,before_json,after_json,memory_id) VALUES (?,?,?,?,?)''',
                (result.action_id, row.key, draft['baseline'], unit_value(after),
                 None if existing else memory_id))
            ctx.conn.execute('UPDATE job_results SET applied=1 WHERE job_id=? AND key=?', (job_id, row.key))
            result.changed.append(row.key)
        remaining = ctx.conn.execute('SELECT COUNT(*) FROM job_results WHERE job_id=? AND applied=0',
                                     (job_id,)).fetchone()[0]
        ctx.conn.execute('UPDATE translation_jobs SET state=? WHERE id=?',
                         ('partially_applied' if remaining else 'applied', job_id))
    return result


def preview_undo(conn, action_id: str) -> list[ChangePreview]:
    action = conn.execute('SELECT * FROM translation_actions WHERE id=?', (action_id,)).fetchone()
    if not action:
        raise ValueError('Action not found')
    units = get_units(conn, action['project_id'])
    out = []
    for r in conn.execute('SELECT * FROM action_rows WHERE action_id=? AND undone=0', (action_id,)):
        before = json.loads(r['before_json']) or {}
        current = dict(units.get(r['key']) or {})
        conflict = unit_value(units.get(r['key'])) != r['after_json']
        out.append(ChangePreview(r['key'], before.get('source_text', ''), current.get('target_text', ''),
                                 before.get('target_text', ''), 'blocked' if conflict else 'restore',
                                 'Later edits are preserved' if conflict else ''))
    return out


def undo_action(conn, action_id: str, keys: set[str] | None = None) -> ActionResult:
    preview = preview_undo(conn, action_id)
    action = conn.execute('SELECT * FROM translation_actions WHERE id=?', (action_id,)).fetchone()
    result = ActionResult(action_id)
    with conn:
        for row in preview:
            if keys is not None and row.key not in keys:
                continue
            if row.change == 'blocked':
                result.conflicts.append((row.key, row.reason))
                continue
            entry = conn.execute('SELECT * FROM action_rows WHERE action_id=? AND key=?',
                                 (action_id, row.key)).fetchone()
            before = json.loads(entry['before_json'])
            conn.execute('DELETE FROM translation_units WHERE project_id=? AND key=?',
                         (action['project_id'], row.key))
            if before:
                columns = list(before)
                conn.execute(f"INSERT INTO translation_units ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                             list(before.values()))
            if entry['memory_id']:
                # Keep a variant already reused by another active translation.
                conn.execute('''DELETE FROM translation_memory WHERE id=? AND NOT EXISTS
                    (SELECT 1 FROM translation_units WHERE target_text=translation_memory.target_text
                     AND source_text=translation_memory.source_text)''', (entry['memory_id'],))
            if action['kind'] == 'remove_service':
                conn.execute('DELETE FROM memory_suppressions WHERE project_id=? AND key=?',
                             (action['project_id'], row.key))
                for memory_id in json.loads(entry['suppression_json']):
                    conn.execute('INSERT OR IGNORE INTO memory_suppressions VALUES (?,?,?)',
                                 (action['project_id'], row.key, memory_id))
            conn.execute('UPDATE action_rows SET undone=1 WHERE action_id=? AND key=?', (action_id, row.key))
            result.changed.append(row.key)
        left = conn.execute('SELECT COUNT(*) FROM action_rows WHERE action_id=? AND undone=0', (action_id,)).fetchone()[0]
        conn.execute('UPDATE translation_actions SET undone=? WHERE id=?', (not left, action_id))
    return result


def discard_job(conn, job_id: str) -> None:
    with conn:
        conn.execute('DELETE FROM job_results WHERE job_id=? AND applied=0', (job_id,))
        conn.execute("UPDATE translation_jobs SET state='discarded' WHERE id=?", (job_id,))


def preview_service_removal(ctx) -> list[ChangePreview]:
    return [ChangePreview(k, u['source_text'], u['target_text'], '', 'remove')
            for k, raw in get_units(ctx.conn, ctx.project_id).items()
            if removable(u := dict(raw)) and k in ctx.source_values]


def remove_service_translations(ctx, selection: dict[str, str], *, update_game_files: bool = False) -> ActionResult:
    """Selection maps keys to the exact unit baseline shown in the preview."""
    from .writer import apply_write_plan, build_write_plan, prepare_write_plan
    result = ActionResult(uuid.uuid4().hex)
    units = get_units(ctx.conn, ctx.project_id)
    chosen = {}
    for key, baseline in selection.items():
        raw = units.get(key)
        if raw is None or unit_value(raw) != baseline or not removable(dict(raw)):
            result.conflicts.append((key, 'Translation changed or is protected'))
        else:
            chosen[key] = dict(raw)
    # Prepare file changes before mutating the database; writer rolls back disk on failure.
    plan = None
    if update_game_files:
        plan = build_write_plan(ctx.scan, ctx.project, {k: v for k, v in units.items() if k not in chosen})
        prepare_write_plan(ctx.conn, ctx.project_id, plan)
    ctx.conn.execute('SAVEPOINT remove_service')
    try:
        ctx.conn.execute('INSERT INTO translation_actions VALUES (?,?,?,?,0)',
                         (result.action_id, ctx.project_id, 'remove_service', _now()))
        for key, unit in chosen.items():
            suppressed = [r[0] for r in ctx.conn.execute('SELECT memory_id FROM memory_suppressions WHERE project_id=? AND key=?',
                                                       (ctx.project_id, key))]
            ctx.conn.execute('''INSERT INTO action_rows
                (action_id,key,before_json,after_json,suppression_json) VALUES (?,?,?,'null',?)''',
                (result.action_id, key, unit_value(unit), encode(suppressed)))
            ctx.conn.execute('''INSERT OR IGNORE INTO memory_suppressions
                SELECT ?,?,id FROM translation_memory WHERE source_text=? AND target_text=?
                AND source_lang=? AND target_lang=? AND origin_kind='service' ''',
                (ctx.project_id, key, unit['source_text'], unit['target_text'],
                 ctx.project['source_lang'], ctx.project['target_lang']))
            ctx.conn.execute('DELETE FROM translation_units WHERE project_id=? AND key=?', (ctx.project_id, key))
            result.changed.append(key)
        if plan is not None and chosen:
            apply_write_plan(ctx.conn, ctx.project_id, plan, ctx.scan, units, commit=False)
        ctx.conn.execute('RELEASE remove_service')
        ctx.conn.commit()
    except Exception:
        ctx.conn.execute('ROLLBACK TO remove_service')
        ctx.conn.execute('RELEASE remove_service')
        raise
    return result


def recover_interrupted(conn) -> list[dict]:
    """После перезапуска: прерванные задания честно помечаются остановленными.

    Возвращает задания, где остались неприменённые черновики или
    непереведённые строки, чтобы интерфейс предложил продолжить.
    """
    with conn:
        conn.execute("UPDATE translation_jobs SET state='stopped' WHERE state='running'")
    # Только прерванный перевод с оставшимися строками; проверенный импорт, где
    # замены сознательно не применили, не должен напоминать о себе при каждом запуске.
    return [dict(r) for r in conn.execute(
        '''SELECT j.*, COUNT(r.key) AS pending FROM translation_jobs j
           JOIN job_results r ON r.job_id=j.id AND r.applied=0 AND r.target_text IS NULL
           WHERE j.state IN ('stopped','paused','failed')
           GROUP BY j.id ORDER BY j.created_at DESC''')]
