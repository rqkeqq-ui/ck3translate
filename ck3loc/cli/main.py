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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
