"""Draft, exchange and history CLI uses the same operations as the desktop UI."""
from __future__ import annotations
import json
import signal
from pathlib import Path
from ck3loc.core import db
from ck3loc.core.ops import load_project_context, rows_to_translate
from ck3loc.core.exchange import plan_export, write_export, import_files, stage_import, route_files, result_files
from ck3loc.core.jobs import (CancellationToken, encode, unit_value, preview_job, apply_job,
                             preview_undo, undo_action, discard_job, preview_service_removal,
                             remove_service_translations)


def read_keys(path, mod_id='') -> set[str]:
    if not path:
        return set()
    text = Path(path).read_text(encoding='utf-8-sig')
    try:
        rows = json.loads(text)
    except ValueError:
        return {s.strip() for s in text.splitlines() if s.strip()}
    if not isinstance(rows, list):
        raise ValueError('Selection must be a JSON list')
    return {r if isinstance(r, str) else r['key'] for r in rows
            if isinstance(r, str) or r.get('mod_id') == mod_id}


def context(conn, args):
    ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    if ctx is None:
        raise ValueError(f'Mod {args.mod_id} unavailable')
    return ctx


def export(args):
    conn = db.connect()
    try:
        ctx = context(conn, args)
        plan = plan_export(ctx, Path(args.output or f'{args.mod_id}_{args.target}_task'),
                           args.fmt, args.what, read_keys(args.keys_file, args.mod_id), args.part_size)
        print(encode({'export_id':plan.export_id,'rows':plan.unit_count,'parts':[
            {'path':str(p.path),'rows':len(p.rows)} for p in plan.parts]}))
        if not args.dry_run:
            write_export(ctx, plan)
        return 0
    finally:
        conn.close()


def import_results(args):
    conn = db.connect()
    try:
        ctx = context(conn, args)
        report = import_files(ctx, [Path(p) for p in args.file], args.export_id)
        print(encode({'accepted':len(report.accepted),'rejected':[r.__dict__ for r in report.rejected],
                      'warnings':report.warnings,'fatal':report.fatal}))
        if not report.ok:
            return 1
        if args.policy == 'replace-selected' and not args.keys_file:
            raise ValueError('Replacement requires --keys-file')
        if not args.dry_run:
            job = stage_import(ctx, report, args.provider)
            preview = preview_job(ctx, job)
            print(encode({'job_id':job,'preview':[r.__dict__ for r in preview]}))
            keys = read_keys(args.keys_file, args.mod_id) if args.policy == 'replace-selected' else None
            print(encode(apply_job(ctx, job, keys).__dict__))
        return 0
    finally:
        conn.close()


def translate(args):
    from ck3loc.core.pipeline import plan_translation, translate_rows
    from ck3loc.providers.registry import make_provider, PROVIDERS
    conn = db.connect()
    try:
        ctx = context(conn, args)
        rows = rows_to_translate(ctx, args.what, read_keys(args.keys_file, args.mod_id))
        options = dict(retranslate=args.retranslate, rows_per_request=args.rows_per_request,
                       use_memory=not args.no_memory, use_vanilla=not args.no_vanilla,
                       allow_service_memory=args.allow_service_memory,
                       workers=args.workers, request_pause=args.pause)
        planned = plan_translation(ctx, rows, args.provider, **options)
        batch_size = min(args.rows_per_request, PROVIDERS[args.provider].batch_size)
        api_rows = sum(not r['reuse'] for r in planned)
        print(encode({'project_id':ctx.project_id,'rows':planned,'requests':(api_rows+batch_size-1)//batch_size}))
        if args.dry_run or args.estimate_only:
            return 0
        token = CancellationToken()
        previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, lambda *_: token.cancel())
        try:
            stats = translate_rows(ctx, rows, make_provider(args.provider), cancellation=token, **options)
            print(encode(stats.__dict__))
            return 0 if stats.state == 'completed' else 1
        finally:
            signal.signal(signal.SIGINT, previous)
    finally:
        conn.close()


def batch_export(args):
    ids = json.loads(Path(args.mods_file).read_text(encoding='utf-8-sig'))
    if not isinstance(ids, list):
        raise ValueError('Mods file must be a JSON list of mod IDs or selections')
    conn = db.connect()
    try:
        plans = []
        root = Path(args.output)
        for selection in ids:
            mod_id = selection if isinstance(selection, str) else selection['mod_id']
            ctx = load_project_context(conn, mod_id, args.source, args.target)
            if ctx is None:
                print(f'{mod_id}: unavailable')
                continue
            keys = set(selection.get('keys', [])) if isinstance(selection, dict) and 'keys' in selection else None
            plan = plan_export(ctx, root/f'project_{ctx.project_id}', args.fmt,
                               'selected' if keys is not None else args.what, keys, args.part_size)
            plans.append((ctx,plan))
        print(encode({'rows':sum(p.unit_count for _,p in plans),'parts':sum(len(p.parts) for _,p in plans),
                      'projects':[{'mod_id':c.project['mod_id'],'files':[str(x.path) for x in p.parts]} for c,p in plans]}))
        if not args.dry_run and any(p.parts for _,p in plans):
            if (root/'batch-manifest.json').exists():
                raise FileExistsError(root/'batch-manifest.json')
            for ctx,plan in plans:
                write_export(ctx,plan)
            (root/'batch-manifest.json').write_text(encode([{'export_id':p.export_id,'project_id':p.project_id} for _,p in plans]),encoding='utf-8')
        return 0
    finally:
        conn.close()


def batch_import(args):
    paths = [Path(p) for p in args.files or []]
    if args.directory:
        paths += result_files(Path(args.directory))
    conn = db.connect()
    try:
        routed, errors = route_files(conn, paths)
        for pid, paths in routed.items():
            project = conn.execute('SELECT * FROM translation_projects WHERE id=?',(pid,)).fetchone()
            ctx = load_project_context(conn,project['mod_id'],project['source_lang'],project['target_lang'])
            if not ctx:
                errors.append(f"{project['mod_id']}: unavailable")
                continue
            report = import_files(ctx,paths)
            print(encode({'project_id':pid,'accepted':len(report.accepted),'rejected':[r.__dict__ for r in report.rejected],
                          'warnings':report.warnings,'fatal':report.fatal}))
            if report.ok and not args.dry_run:
                print(encode({'project_id':pid,'job_id':stage_import(ctx,report)}))
        print(encode({'errors':errors}))
        return int(bool(errors))
    finally:
        conn.close()


def batch(args):
    from ck3loc.core.mod_library import discover_mods
    from ck3loc.core.pipeline import plan_translation, translate_rows
    from ck3loc.providers.registry import make_provider
    conn = db.connect()
    token = CancellationToken()
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: token.cancel())
    try:
        queue=[]
        for mod in discover_mods(Path(args.steam) if args.steam else None).mods:
            ctx=load_project_context(conn,mod.mod_id,args.source,args.target,mod_dir=mod.path)
            rows=rows_to_translate(ctx,'missing') if ctx else []
            if rows:
                queue.append((ctx,rows))
        if args.limit:
            queue=queue[:args.limit]
        for ctx,rows in queue:
            print(encode({'mod_id':ctx.project['mod_id'],'plan':plan_translation(ctx,rows,args.provider,
                         rows_per_request=args.rows_per_request)}))
        if not args.dry_run:
            provider=make_provider(args.provider)
            for ctx,rows in queue:
                if token.cancelled:
                    break
                stats=translate_rows(ctx,rows,provider,cancellation=token,rows_per_request=args.rows_per_request)
                print(encode(stats.__dict__))
                if stats.state in {'paused','stopped'}:
                    break
        return 0
    finally:
        signal.signal(signal.SIGINT,previous)
        conn.close()


def jobs(args):
    conn=db.connect()
    try:
        if args.action=='list':
            print(encode([dict(r) for r in conn.execute('SELECT * FROM translation_jobs ORDER BY rowid DESC')]))
            return 0
        if args.action=='undo':
            print(encode([r.__dict__ for r in preview_undo(conn,args.id)]))
            if args.apply:
                print(encode(undo_action(conn,args.id,read_keys(args.keys_file) if args.keys_file else None).__dict__))
            return 0
        if args.action=='discard':
            discard_job(conn,args.id)
            return 0
        job=conn.execute('SELECT * FROM translation_jobs WHERE id=?',(args.id,)).fetchone()
        if not job:
            raise ValueError('Unknown job')
        project=conn.execute('SELECT * FROM translation_projects WHERE id=?',(job['project_id'],)).fetchone()
        ctx=load_project_context(conn,project['mod_id'],project['source_lang'],project['target_lang'])
        if not ctx:
            raise ValueError('Mod unavailable')
        if args.action=='apply':
            print(encode([r.__dict__ for r in preview_job(ctx,args.id)]))
            if args.apply:
                print(encode(apply_job(ctx,args.id,read_keys(args.keys_file,project['mod_id']) if args.keys_file else None).__dict__))
        elif args.action=='resume':
            from ck3loc.core.pipeline import translate_rows
            from ck3loc.providers.registry import make_provider
            rows=[{'key':r['key'],'source':r['source_text']} for r in conn.execute('SELECT * FROM job_results WHERE job_id=?',(args.id,))]
            options=json.loads(job['options'])
            options.pop('export_id',None)
            if args.rows_per_request:
                options['rows_per_request']=args.rows_per_request
            token=CancellationToken()
            previous=signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT,lambda *_:token.cancel())
            try:
                print(encode(translate_rows(ctx,rows,make_provider(args.provider or job['provider']),job_id=args.id,cancellation=token,**options).__dict__))
            finally:
                signal.signal(signal.SIGINT,previous)
        return 0
    finally:
        conn.close()


def remove_services(args):
    selections=json.loads(Path(args.selection).read_text(encoding='utf-8-sig'))
    conn=db.connect()
    try:
        grouped={}
        for row in selections:
            grouped.setdefault(row['mod_id'],[]).append(row)
        for mod_id, selection in grouped.items():
            ctx=load_project_context(conn,mod_id,args.source,args.target)
            if not ctx:
                print(f'{mod_id}: unavailable')
                continue
            candidates={r.key:r for r in preview_service_removal(ctx)}
            keys={r['key'] for r in selection} & set(candidates)
            print(encode({'mod_id':mod_id,'rows':[candidates[k].__dict__ for k in sorted(keys)]}))
            if args.apply and not args.dry_run:
                baselines={k:unit_value(ctx.units[k]) for k in keys}
                print(encode(remove_service_translations(ctx,baselines,update_game_files=args.update_game_files).__dict__))
        return 0
    finally:
        conn.close()


def chatgpt(args):
    from ck3loc.providers import chatgpt as provider
    if args.action=='login':
        print(encode(provider.login(args.account or '')))
    elif args.action=='accounts':
        print(encode(provider.accounts()))
    elif args.action=='use':
        provider.use_account(args.account)
    elif args.action=='logout':
        print('Revocation confirmed' if provider.logout(args.account or '') else 'Local sign-out; remote revocation unconfirmed')
    elif args.action=='models':
        print(encode(provider.models(args.account or '')))
    return 0


def register(sub):
    existing=sub.choices
    pe=existing['export']
    pe.set_defaults(func=export)
    pe._option_string_actions['--fmt'].choices=['jsonl','xliff','yml']
    pe._option_string_actions['--what'].choices.append('selected')
    pe.add_argument('--keys-file')
    pe.add_argument('--part-size',type=positive)
    pe.add_argument('--dry-run',action='store_true')
    pi=existing['import']
    pi.set_defaults(func=import_results)
    next(a for a in pi._actions if a.dest=='file').nargs='+'
    pi.add_argument('--policy',choices=['missing-only','replace-selected'],default='missing-only')
    pi.add_argument('--keys-file')
    pi.add_argument('--export-id')
    pi.add_argument('--provider')
    pi.add_argument('--dry-run',action='store_true')
    for name,callback in [('translate',translate),('batch',batch)]:
        parser=existing[name]
        parser.set_defaults(func=callback)
        choices=parser._option_string_actions['--provider'].choices
        if 'chatgpt' not in choices:
            choices.append('chatgpt')
        parser.add_argument('--rows-per-request',type=positive,default=40)
        parser.add_argument('--dry-run',action='store_true')
    from ck3loc.core.pipeline import MAX_WORKERS
    pt=existing['translate']
    pt.add_argument('--workers',type=int,choices=range(1,MAX_WORKERS+1),default=1,metavar='N',
                    help=f'одновременных запросов (1–{MAX_WORKERS})')
    pt.add_argument('--pause',type=float,default=0.0,help='пауза между запросами, секунд')
    pt=existing['translate']
    pt._option_string_actions['--what'].choices.append('selected')
    pt.add_argument('--keys-file')
    pt.add_argument('--retranslate',action='store_true')
    pt.add_argument('--no-memory',action='store_true')
    pt.add_argument('--no-vanilla',action='store_true')
    pt.add_argument('--allow-service-memory',action='store_true')
    def langs(p):
        p.add_argument('--source',default='english')
        p.add_argument('--target',default='russian')
    p=sub.add_parser('batch-export')
    p.add_argument('--mods-file',required=True)
    p.add_argument('--fmt',choices=['jsonl','xliff','yml'],default='jsonl')
    p.add_argument('--what',choices=['missing','outdated','stale','all'],default='missing')
    p.add_argument('--part-size',type=positive)
    p.add_argument('-o','--output',required=True)
    p.add_argument('--dry-run',action='store_true')
    langs(p)
    p.set_defaults(func=batch_export)
    p=sub.add_parser('batch-import')
    p.add_argument('--files',nargs='+')
    p.add_argument('--directory')
    p.add_argument('--dry-run',action='store_true')
    p.set_defaults(func=batch_import)
    p=sub.add_parser('jobs')
    p.add_argument('action',choices=['list','resume','discard','apply','undo'])
    p.add_argument('id',nargs='?')
    p.add_argument('--apply',action='store_true')
    p.add_argument('--keys-file')
    p.add_argument('--provider')
    p.add_argument('--rows-per-request',type=positive)
    p.set_defaults(func=jobs)
    p=sub.add_parser('remove-service-translations')
    p.add_argument('--selection',required=True)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--apply',action='store_true')
    p.add_argument('--update-game-files',action='store_true')
    langs(p)
    p.set_defaults(func=remove_services)
    p=sub.add_parser('chatgpt')
    p.add_argument('action',choices=['login','accounts','use','logout','models'])
    p.add_argument('account',nargs='?')
    p.set_defaults(func=chatgpt)


def positive(value):
    from argparse import ArgumentTypeError
    try:
        result=int(value)
        if result>0:
            return result
    except ValueError:
        pass
    raise ArgumentTypeError('Expected a positive integer')
