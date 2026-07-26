"""CLI: все операции ядра из командной строки.

  python -m ck3loc scan [--steam PATH] [--source LANG] [--target LANG]
  python -m ck3loc report <mod_id> [--source LANG] [--target LANG] [--full]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ck3loc.core.scanner import scan_mod
from ck3loc.core.steam import (
    find_steam_root,
    list_workshop_mod_dirs,
    read_workshop_acf,
    workshop_content_dirs,
)
from ck3loc.core.vanilla import find_ck3_game_dir, game_languages


def _resolve_mods(steam_path: str | None) -> tuple[list[Path], list[str]]:
    override = Path(steam_path) if steam_path else None
    root = find_steam_root(override)
    if root is None:
        print("Steam не найден. Укажите путь: --steam <папка Steam>")
        return [], []
    content = workshop_content_dirs(root)
    if not content:
        print(f"Папка мастерской CK3 не найдена в библиотеках Steam ({root}).")
        return [], []
    langs = game_languages()
    return list_workshop_mod_dirs(content), langs


def cmd_scan(args: argparse.Namespace) -> int:
    mod_dirs, langs = _resolve_mods(args.steam)
    if not mod_dirs:
        return 1
    source, target = args.source, args.target
    game = find_ck3_game_dir()
    print(f"Языки игры: {', '.join(langs)}" if game else "Игра CK3 не найдена (используется резервный список языков)")

    total = len(mod_dirs)
    with_loc = 0
    no_target = 0
    partial = 0
    with_errors = 0
    rows = []
    for mod_dir in mod_dirs:
        scan = scan_mod(mod_dir, langs)
        if not scan.has_localization:
            rows.append((scan.mod_id, scan.name, 0, "-", "нет локализации"))
            continue
        with_loc += 1
        src = scan.best_source_language(source) or source
        translated, of = scan.coverage(target, src)
        errors = [d for _p, d in scan.diagnostics if d.severity == "error"]
        if errors:
            with_errors += 1
        if of == 0:
            state = f"нет {src}"
            cov = "-"
        elif translated == 0:
            no_target += 1
            state = f"нет {target}"
            cov = "0%"
        elif translated < of:
            partial += 1
            state = f"{of - translated} пропущено"
            cov = f"{100 * translated / of:.1f}%"
        else:
            state = "полный"
            cov = "100%"
        rows.append(
            (scan.mod_id, scan.name, len(scan.languages), cov, state)
        )

    print()
    print(f"Модов установлено: {total}")
    print(f"Содержат локализацию: {with_loc}")
    print(f"Нет языка {target}: {no_target}")
    print(f"Язык {target} неполный: {partial}")
    print(f"С ошибками в файлах: {with_errors}")
    print()
    wid = max((len(r[1]) for r in rows), default=10)
    wid = min(wid, 48)
    print(f"{'ID':<12} {'Название':<{wid}} {'Языки':>5} {target + ' %':>8}  Состояние")
    for mod_id, name, nlang, cov, state in rows:
        print(f"{mod_id:<12} {name[:wid]:<{wid}} {nlang:>5} {cov:>8}  {state}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    mod_dirs, langs = _resolve_mods(args.steam)
    match = [d for d in mod_dirs if d.name == args.mod_id]
    if not match:
        print(f"Мод {args.mod_id} не найден в мастерской.")
        return 1
    scan = scan_mod(match[0], langs)
    d = scan.descriptor
    acf = read_workshop_acf()
    print(f"Мод: {scan.name}  (ID {scan.mod_id})")
    print(f"Папка: {scan.mod_dir}")
    if d.exists:
        print(f"descriptor.mod: version={d.version or '—'} "
              f"supported_version={d.supported_version or '—'}")
    else:
        print("descriptor.mod: отсутствует")
    entry = acf.get(scan.mod_id)
    if entry and entry.time_updated:
        import datetime

        ts = datetime.datetime.fromtimestamp(int(entry.time_updated))
        print(f"Обновлён (по данным Steam): {ts:%d.%m.%Y %H:%M}")
    print()
    if not scan.has_localization:
        print("Локализации нет.")
        return 0

    src = scan.best_source_language(args.source) or args.source
    if src != args.source:
        print(f"Внимание: самый полный язык — {src}, он взят источником.")
    print(f"{'Язык':<14} {'Файлов':>6} {'Ключей':>7}  Полнота (от {src})")
    src_count = scan.languages.get(src)
    for lang in sorted(scan.languages):
        s = scan.languages[lang]
        translated, of = scan.coverage(lang, src)
        cov = f"{100 * translated / of:.1f}%" if of else "—"
        print(f"{lang:<14} {s.file_count:>6} {s.key_count:>7}  {cov}")

    missing = scan.missing_keys(args.target, src)
    extra = scan.extra_keys(args.target, src)
    print()
    print(f"Пропущено в {args.target}: {len(missing)}")
    limit = None if args.full else 20
    for k in missing[:limit]:
        occ = scan.languages[src].keys[k]
        print(f"  {k}: \"{occ.value[:70]}\"")
    if limit and len(missing) > limit:
        print(f"  … ещё {len(missing) - limit} (используйте --full)")
    print(f"Только в {args.target} (требуют взгляда человека): {len(extra)}")
    for k in extra[:limit]:
        print(f"  {k}")
    if scan.diagnostics:
        print()
        print(f"Диагностика ({len(scan.diagnostics)}):")
        shown = scan.diagnostics if args.full else scan.diagnostics[:15]
        for rel, diag in shown:
            print(f"  [{diag.severity}] {rel}:{diag.lineno} {diag.code}: {diag.message}")
        if not args.full and len(scan.diagnostics) > 15:
            print(f"  … ещё {len(scan.diagnostics) - 15} (используйте --full)")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.store import mark_missing_mods, record_mod, take_snapshot

    mod_dirs, langs = _resolve_mods(args.steam)
    if not mod_dirs:
        return 1
    if args.mod_id:
        mod_dirs = [d for d in mod_dirs if d.name == args.mod_id]
        if not mod_dirs:
            print(f"Мод {args.mod_id} не найден.")
            return 1
    conn = db.connect()
    acf = read_workshop_acf()
    new_count = 0
    for mod_dir in mod_dirs:
        scan = scan_mod(mod_dir, langs)
        entry = acf.get(scan.mod_id)
        t_upd = int(entry.time_updated) if entry and entry.time_updated else 0
        record_mod(conn, scan, steam_time_updated=t_upd)
        if scan.has_localization:
            res = take_snapshot(conn, scan, steam_time_updated=t_upd)
            if res.is_new:
                new_count += 1
                print(f"  снимок: {scan.name} ({scan.mod_id})")
    if not args.mod_id:
        gone = mark_missing_mods(conn, {d.name for d in mod_dirs})
        for g in gone:
            print(f"  больше не установлен: {g} (данные сохранены)")
    print(f"Готово: новых снимков {new_count} из {len(mod_dirs)} модов.")
    conn.close()
    return 0


def cmd_changes(args: argparse.Namespace) -> int:
    from ck3loc.core import db

    conn = db.connect()
    snaps = conn.execute(
        "SELECT * FROM mod_snapshots WHERE mod_id=? ORDER BY id DESC LIMIT 2",
        (args.mod_id,),
    ).fetchall()
    if len(snaps) == 0:
        print("Снимков нет — сначала выполните: ck3loc snapshot")
        return 1
    if len(snaps) == 1:
        print("Снимок один — изменений отслеживать не с чем. Это точка отсчёта.")
        return 0
    new, old = snaps[0], snaps[1]
    from ck3loc.core.store import diff_snapshots, snapshot_language

    langs = conn.execute(
        "SELECT DISTINCT language FROM snapshot_entries WHERE snapshot_id=?",
        (new["id"],),
    ).fetchall()
    print(f"Мод {args.mod_id}: снимок {old['taken_at']} → {new['taken_at']}")
    any_change = False
    for lr in langs:
        lang = lr["language"]
        diff = diff_snapshots(conn, old["id"], new["id"], lang)
        if diff.empty:
            continue
        any_change = True
        print(f"\n[{lang}] новых: {len(diff.added)}, изменённых: "
              f"{len(diff.changed)}, удалённых: {len(diff.removed)}")
        newvals = snapshot_language(conn, new["id"], lang)
        oldvals = snapshot_language(conn, old["id"], lang)
        for k in diff.added[:10]:
            print(f"  + {k}: \"{newvals[k]['value'][:60]}\"")
        for k in diff.changed[:10]:
            print(f"  ~ {k}:")
            print(f"      было:  \"{oldvals[k]['value'][:60]}\"")
            print(f"      стало: \"{newvals[k]['value'][:60]}\"")
        for k in diff.removed[:10]:
            print(f"  - {k}")
    if not any_change:
        print("Локализация между двумя последними снимками не менялась.")
    conn.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.bundle import export_jsonl
    from ck3loc.core.ops import load_project_context, rows_to_translate
    from ck3loc.core.xliff import export_xliff

    conn = db.connect()
    ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    if ctx is None:
        print(f"Мод {args.mod_id} не найден.")
        return 1
    rows = rows_to_translate(ctx, args.what)
    if not rows:
        print("Строк для экспорта нет — всё переведено и актуально.")
        return 0
    out = Path(args.output) if args.output else Path.cwd() / (
        f"{args.mod_id}_{args.target}.{ 'xliff' if args.fmt == 'xliff' else 'jsonl'}"
    )
    if args.fmt == "xliff":
        res = export_xliff(conn, ctx.project_id, rows, out,
                           ctx.project["source_lang"], args.target)
        print(f"Экспортировано строк: {res.unit_count}")
        print(f"Файл: {res.path}")
    else:
        res = export_jsonl(conn, ctx.project_id, rows, out,
                           ctx.project["source_lang"], args.target)
        print(f"Экспортировано строк: {res.unit_count}")
        print(f"Файл задания: {res.path}")
        print(f"Промпт для LLM: {res.prompt_path}")
    conn.close()
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.bundle import import_jsonl
    from ck3loc.core.ops import apply_import_report, load_project_context
    from ck3loc.core.xliff import import_xliff

    conn = db.connect()
    ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    if ctx is None:
        print(f"Мод {args.mod_id} не найден.")
        return 1
    path = Path(args.file)
    if path.suffix.lower() in (".xliff", ".xlf"):
        report = import_xliff(conn, path, ctx.source_values)
    else:
        report = import_jsonl(conn, path, ctx.source_values)
    if not report.ok:
        print(f"Импорт остановлен: {report.fatal}")
        return 1
    n = apply_import_report(ctx, report)
    print(f"Принято: {n}")
    if report.rejected:
        print(f"Отклонено: {len(report.rejected)}")
        for r in report.rejected[:15]:
            print(f"  {r.key}: {r.reason}")
        if len(report.rejected) > 15:
            print(f"  … ещё {len(report.rejected) - 15}")
    conn.close()
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.ops import load_project_context
    from ck3loc.core.store import set_project_option
    from ck3loc.core.writer import apply_write_plan, build_write_plan

    conn = db.connect()
    ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    if ctx is None:
        print(f"Мод {args.mod_id} не найден.")
        return 1
    if args.mode and args.mode != ctx.project["write_mode"]:
        from ck3loc.core.writer import remove_outputs

        removed = remove_outputs(conn, ctx.project_id, args.mod_id)
        if removed:
            print(f"Режим записи изменён: удалено файлов прежнего режима "
                  f"{len(removed)} (резервные копии сохранены).")
        set_project_option(conn, ctx.project_id, "write_mode", args.mode)
        ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    plan = build_write_plan(ctx.scan, ctx.project, ctx.units, args.build)
    print(f"Режим записи: {plan.write_mode}, сборка: {plan.build_mode}")
    print(f"Файлов будет записано: {len(plan.files)}, ключей: {plan.total_keys}")
    for f in plan.files:
        print(f"  {f.abs_path}  ({len(f.keys)} ключей)" if f.keys
              else f"  {f.abs_path}")
    if plan.skipped_keys:
        print(f"Пропущено строк: {len(plan.skipped_keys)}")
        for key, reason in plan.skipped_keys[:10]:
            print(f"  {key}: {reason}")
    if args.dry_run:
        print("Пробный прогон — на диск ничего не записано.")
        return 0
    if plan.total_keys == 0:
        print("Записывать нечего.")
        return 0
    result = apply_write_plan(conn, ctx.project_id, plan, ctx.scan, ctx.units)
    print(f"Записано файлов: {len(result.written)}"
          + (f", резервных копий: {len(result.backups)}" if result.backups else ""))
    if plan.write_mode == "patch_mod":
        print("Не забудьте включить патч-мод в плейсете ПОСЛЕ оригинального мода.")
    conn.close()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.ops import load_project_context
    from ck3loc.core.writer import apply_write_plan, build_write_plan, verify_outputs

    conn = db.connect()
    ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    if ctx is None:
        print(f"Мод {args.mod_id} не найден.")
        return 1
    checks = verify_outputs(conn, ctx.project_id)
    if not checks:
        print("Для этого мода приложение ещё ничего не записывало.")
        return 0
    bad = [c for c in checks if c.state != "ok"]
    for c in checks:
        mark = {"ok": "✓", "missing": "✗ стёрт", "modified": "! изменён извне"}[c.state]
        print(f"  {mark}  {c.path}")
    if not bad:
        print("Все записанные файлы на месте и не изменены.")
        return 0
    if args.restore:
        plan = build_write_plan(ctx.scan, ctx.project, ctx.units)
        apply_write_plan(conn, ctx.project_id, plan, ctx.scan, ctx.units)
        print(f"Восстановлено из базы: {len(plan.files)} файлов.")
    else:
        print("Запустите с --restore, чтобы восстановить из базы.")
    conn.close()
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    from ck3loc.providers.registry import PROVIDERS, set_api_key

    if args.provider not in PROVIDERS:
        print(f"Неизвестный провайдер. Доступны: {', '.join(PROVIDERS)}")
        return 1
    if args.action == "set":
        import getpass

        key = getpass.getpass(f"API-ключ для {args.provider}: ")
        if not key:
            print("Пустой ключ — ничего не сохранено.")
            return 1
        set_api_key(args.provider, key)
        print("Ключ сохранён в хранилище Windows (Credential Manager).")
    else:
        set_api_key(args.provider, "")
        print("Ключ удалён.")
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.glossary_seed import seed_glossary
    from ck3loc.core.ops import load_project_context, rows_to_translate
    from ck3loc.core.pipeline import build_vanilla_lookup, estimate, translate_rows
    from ck3loc.providers.base import ProviderError
    from ck3loc.providers.registry import make_provider

    conn = db.connect()
    seed_glossary(conn)
    ctx = load_project_context(conn, args.mod_id, args.source, args.target)
    if ctx is None:
        print(f"Мод {args.mod_id} не найден.")
        return 1
    rows = rows_to_translate(ctx, args.what)
    if not rows:
        print("Переводить нечего — всё актуально.")
        return 0
    vl = build_vanilla_lookup(ctx.project["source_lang"],
                              ctx.project["target_lang"])
    est = estimate(ctx, rows, vanilla_lookup=vl)
    print(f"Строк на перевод: {est.rows}")
    print(f"Закроется ванилью CK3 (бесплатно): {est.covered_by_vanilla}")
    print(f"Закроется памятью переводов (бесплатно): {est.covered_by_memory}")
    print(f"Пойдёт в API: {est.rows - est.covered_by_vanilla - est.covered_by_memory} "
          f"строк, ~{est.chars_to_api} символов")
    if args.estimate_only:
        return 0
    try:
        provider = make_provider(args.provider)
    except ProviderError as e:
        print(e)
        return 1

    def progress(done, total):
        print(f"\r  переведено {done}/{total}", end="", flush=True)

    try:
        stats = translate_rows(ctx, rows, provider, progress_cb=progress,
                               vanilla_lookup=vl)
    except ProviderError as e:
        print(f"\nОшибка провайдера: {e}")
        return 1
    print()
    print(f"Готово: ваниль {stats.from_vanilla}, память {stats.from_memory}, "
          f"API {stats.from_api}, ошибок {len(stats.failed)}")
    for key, reason in stats.failed[:10]:
        print(f"  {key}: {reason}")
    print("Теперь запишите перевод: ck3loc write " + args.mod_id)
    conn.close()
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    from ck3loc.core import db
    from ck3loc.core.glossary_seed import seed_glossary
    from ck3loc.core.ops import load_project_context, rows_to_translate
    from ck3loc.core.pipeline import build_vanilla_lookup, translate_rows
    from ck3loc.core.scanner import scan_mod
    from ck3loc.core.writer import apply_write_plan, build_write_plan
    from ck3loc.providers.base import ProviderError
    from ck3loc.providers.registry import make_provider

    mod_dirs, langs = _resolve_mods(args.steam)
    if not mod_dirs:
        return 1
    conn = db.connect()
    seed_glossary(conn)
    try:
        provider = make_provider(args.provider)
    except ProviderError as e:
        print(e)
        return 1
    vl = build_vanilla_lookup(args.source, args.target)

    queue = []
    for mod_dir in mod_dirs:
        scan = scan_mod(mod_dir, langs)
        if not scan.has_localization:
            continue
        src = scan.best_source_language(args.source) or args.source
        translated, of = scan.coverage(args.target, src)
        if of > 0 and translated == 0:
            queue.append(mod_dir)
    if args.limit:
        queue = queue[: args.limit]
    print(f"Модов без языка {args.target}: {len(queue)}")
    for i, mod_dir in enumerate(queue, start=1):
        ctx = load_project_context(conn, mod_dir.name, args.source,
                                   args.target, mod_dir=mod_dir)
        rows = rows_to_translate(ctx, "missing")
        print(f"[{i}/{len(queue)}] {ctx.scan.name}: {len(rows)} строк")
        stats = translate_rows(ctx, rows, provider, vanilla_lookup=vl)
        print(f"    ваниль {stats.from_vanilla}, память {stats.from_memory}, "
              f"API {stats.from_api}, ошибок {len(stats.failed)}")
        ctx = load_project_context(conn, mod_dir.name, args.source,
                                   args.target, mod_dir=mod_dir)
        plan = build_write_plan(ctx.scan, ctx.project, ctx.units)
        if plan.total_keys:
            apply_write_plan(conn, ctx.project_id, plan, ctx.scan, ctx.units)
            print(f"    записано ключей: {plan.total_keys}")
    print("Пакетный перевод завершён.")
    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ck3loc", description="CK3 Localization Manager")
    p.add_argument("--steam", help="путь к папке Steam (если не найдён сам)")
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("scan", help="сводка по всей библиотеке модов")
    ps.add_argument("--source", default="english", help="исходный язык")
    ps.add_argument("--target", default="russian", help="целевой язык")
    ps.set_defaults(func=cmd_scan)

    pr = sub.add_parser("report", help="полный отчёт по одному моду")
    pr.add_argument("mod_id", help="ID мода (имя папки в мастерской)")
    pr.add_argument("--source", default="english")
    pr.add_argument("--target", default="russian")
    pr.add_argument("--full", action="store_true", help="полные списки без сокращений")
    pr.set_defaults(func=cmd_report)

    pn = sub.add_parser("snapshot", help="снять снимки локализаций (все моды или один)")
    pn.add_argument("mod_id", nargs="?", help="ID мода (по умолчанию — вся библиотека)")
    pn.set_defaults(func=cmd_snapshot)

    pc = sub.add_parser("changes", help="что изменилось у мода с прошлого снимка")
    pc.add_argument("mod_id")
    pc.set_defaults(func=cmd_changes)

    def _langs(sp):
        sp.add_argument("--source", default="english")
        sp.add_argument("--target", default="russian")

    pe = sub.add_parser("export", help="выгрузить файл-задание для внешней LLM")
    pe.add_argument("mod_id")
    pe.add_argument("--what",
                    choices=["missing", "stale", "outdated", "all"],
                    default="outdated",
                    help="что выгружать (по умолчанию недостающие+устаревшие)")
    pe.add_argument("--fmt", choices=["jsonl", "xliff"], default="jsonl")
    pe.add_argument("-o", "--output", help="куда сохранить файл")
    _langs(pe)
    pe.set_defaults(func=cmd_export)

    pi = sub.add_parser("import", help="импортировать переведённый файл")
    pi.add_argument("mod_id")
    pi.add_argument("file")
    _langs(pi)
    pi.set_defaults(func=cmd_import)

    pw = sub.add_parser("write", help="записать перевод (внутрь мода или патч-модом)")
    pw.add_argument("mod_id")
    pw.add_argument("--mode", choices=["in_mod", "patch_mod"])
    pw.add_argument("--build", choices=["auto", "full", "delta"], default="auto")
    pw.add_argument("--dry-run", action="store_true", help="показать план без записи")
    _langs(pw)
    pw.set_defaults(func=cmd_write)

    pv = sub.add_parser("verify", help="проверить записанные файлы; --restore для восстановления")
    pv.add_argument("mod_id")
    pv.add_argument("--restore", action="store_true")
    _langs(pv)
    pv.set_defaults(func=cmd_verify)

    pk = sub.add_parser("key", help="сохранить/удалить API-ключ провайдера")
    pk.add_argument("action", choices=["set", "clear"])
    pk.add_argument("provider")
    pk.set_defaults(func=cmd_key)

    pt = sub.add_parser("translate", help="перевести мод встроенным провайдером")
    pt.add_argument("mod_id")
    pt.add_argument("--provider", default="google",
                    choices=["google", "yandex", "deepl", "claude", "openai"])
    pt.add_argument("--what",
                    choices=["missing", "stale", "outdated", "all"],
                    default="outdated")
    pt.add_argument("--estimate-only", action="store_true",
                    help="только смета, без перевода")
    _langs(pt)
    pt.set_defaults(func=cmd_translate)

    pb = sub.add_parser("batch", help="перевести и записать все моды без целевого языка")
    pb.add_argument("--provider", default="google",
                    choices=["google", "yandex", "deepl", "claude", "openai"])
    pb.add_argument("--limit", type=int, help="не больше N модов")
    _langs(pb)
    pb.set_defaults(func=cmd_batch)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
