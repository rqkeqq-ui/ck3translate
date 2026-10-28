"""Exact export plans, split files and multi-project result routing."""
from __future__ import annotations

import json
import os
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .bundle import ImportReport, ImportedUnit, RejectedUnit, PROMPT_TEMPLATE, export_jsonl, import_jsonl
from .glossary_seed import load_glossary, relevant_glossary
from .jobs import create_job, encode, stage_result, unit_value
from .locparser import LocFile, build_new_file
from .ops import rows_to_translate
from .scanner import semantic_hash
from .store import _now, get_units
from .tokens import validate_translation
from .xliff import NS, export_xliff, import_xliff, lang_code

FORMATS = {'jsonl', 'xliff', 'yml'}
SUPPORTED = {'.jsonl', '.xliff', '.xlf', '.yml'}
ARCHIVES = {'.zip'}


@dataclass
class ExportPart:
    path: Path
    rows: list[dict]


@dataclass
class ExportPlan:
    export_id: str
    project_id: int
    fmt: str
    parts: list[ExportPart]
    root: Path
    source_lang: str
    target_lang: str

    @property
    def unit_count(self) -> int:
        return sum(len(p.rows) for p in self.parts)

    @property
    def service_file_count(self) -> int:
        return len(self.parts) + (2 if self.fmt == 'yml' else 1)


def plan_export(ctx, root: Path, fmt: str = 'jsonl', what: str = 'outdated',
                keys: set[str] | None = None, part_size: int | None = None) -> ExportPlan:
    if fmt not in FORMATS:
        raise ValueError('Unsupported export format')
    if part_size is not None and (isinstance(part_size, bool) or not isinstance(part_size, int) or part_size <= 0):
        raise ValueError('Part size must be a positive integer')
    rows = rows_to_translate(ctx, what, keys)
    groups = {}
    for row in rows:
        group = row['rel_path'] if fmt == 'yml' else ''
        groups.setdefault(group, []).append(row)
    chunks = []
    for group, items in sorted(groups.items()):
        limit = part_size or len(items)
        for i in range(0, len(items), limit):
            chunks.append((group, items[i:i + limit]))
    root = Path(root)
    parts = []
    for i, (group, items) in enumerate(chunks, 1):
        name = f'part_{i:03d}_of_{len(chunks):03d}'
        if fmt == 'yml':
            rel = Path(group)
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Unsafe source path')
            path = root / rel.parent / f'{name}_l_{ctx.project["target_lang"]}.yml'
        else:
            path = root / (name + '.' + fmt)
        parts.append(ExportPart(path, items))
    return ExportPlan(uuid.uuid4().hex, ctx.project_id, fmt, parts, root,
                      ctx.project['source_lang'], ctx.project['target_lang'])


def write_export(ctx, plan: ExportPlan) -> list[Path]:
    if plan.project_id != ctx.project_id:
        raise ValueError('Export belongs to another project')
    if not plan.parts:
        return []
    expected = {r['key']: r for p in plan.parts for r in p.rows}
    current = {r['key']: r for r in rows_to_translate(ctx, 'all')}
    if any(current.get(k) != row for k, row in expected.items()):
        raise ValueError('Source or translation changed after export preview')
    paths = [p.path for p in plan.parts] + [p.path.with_suffix('.prompt.txt') for p in plan.parts]
    paths.append(plan.root / 'manifest.json')
    if plan.fmt == 'yml':
        paths.append(plan.root / 'source.json')
    if any(p.exists() for p in paths):
        raise FileExistsError('Export destination already contains task files')
    glossary = load_glossary(ctx.conn, ctx.project['mod_id'], plan.source_lang, plan.target_lang)
    baseline = get_units(ctx.conn, ctx.project_id)
    offset = 0
    for number, part in enumerate(plan.parts, 1):
        if plan.fmt == 'jsonl':
            export_jsonl(ctx.conn, ctx.project_id, part.rows, part.path, plan.source_lang,
                         plan.target_lang, glossary, export_id=plan.export_id, offset=offset)
        elif plan.fmt == 'xliff':
            export_xliff(ctx.conn, ctx.project_id, part.rows, part.path, plan.source_lang,
                         plan.target_lang, export_id=plan.export_id, offset=offset)
        else:
            part.path.parent.mkdir(parents=True, exist_ok=True)
            data = build_new_file(plan.target_lang, [(r['key'], r['current_target'] or r['source']) for r in part.rows])
            part.path.write_bytes(data[:3] + f'# ck3loc-export: {plan.export_id}\r\n'.encode() + data[3:])
            ctx.conn.execute('INSERT OR IGNORE INTO exports VALUES (?,?,?,?,?)',
                             (plan.export_id, ctx.project_id, 'yml', _now(), plan.unit_count))
            ctx.conn.executemany('''INSERT INTO export_units
                (export_id,unit_id,key,source_text,source_hash) VALUES (?,?,?,?,?)''',
                [(plan.export_id, f'u{i:04d}', r['key'], r['source'], semantic_hash(r['source']))
                 for i, r in enumerate(part.rows, offset + 1)])
        for row in part.rows:
            ctx.conn.execute('UPDATE export_units SET baseline=? WHERE export_id=? AND key=?',
                             (unit_value(baseline.get(row['key'])), plan.export_id, row['key']))
        ctx.conn.execute('INSERT INTO export_parts VALUES (?,?,?,?)',
                         (plan.export_id, number, str(part.path.relative_to(plan.root)), encode([r['key'] for r in part.rows])))
        relevant = relevant_glossary(glossary, [r['source'] for r in part.rows])
        prompt = PROMPT_TEMPLATE.format(source_lang=plan.source_lang, target_lang=plan.target_lang,
            mark_open='⟦', mark_close='⟧', glossary_block='\n' + '\n'.join(f'{s} → {t}' for s, t in relevant))
        if plan.fmt != 'jsonl':
            prompt = (f'Translate only target text in {plan.fmt.upper()}; preserve all keys, IDs, '
                      'source text, token metadata and CK3 codes. Return the entire file.\n'
                      f'{plan.source_lang} → {plan.target_lang}\n' + '\n'.join(f'{s} → {t}' for s, t in relevant))
        part.path.with_suffix('.prompt.txt').write_text(prompt, encoding='utf-8')
        offset += len(part.rows)
    manifest = {'export_id': plan.export_id, 'project_id': plan.project_id,
                'mod_id': ctx.project['mod_id'], 'source_lang': plan.source_lang,
                'target_lang': plan.target_lang, 'parts': [
                    {'path': str(p.path.relative_to(plan.root)), 'keys': [r['key'] for r in p.rows]}
                    for p in plan.parts]}
    (plan.root / 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    if plan.fmt == 'yml':
        (plan.root / 'source.json').write_text(encode(list(expected.values())), encoding='utf-8')
    ctx.conn.commit()
    return paths


def file_export_id(path: Path) -> str:
    if path.suffix.lower() == '.jsonl':
        ids = {o.get('export_id', '') for line in path.read_text(encoding='utf-8-sig').splitlines()
               if line.strip() and isinstance(o := json.loads(line), dict)}
        if len(ids) != 1:
            raise ValueError('Missing or mixed export IDs')
        return ids.pop()
    if path.suffix.lower() in {'.xlf', '.xliff'}:
        element = ET.parse(path).getroot().find(f'{{{NS}}}file')
        return element.get('id', '') if element is not None else ''
    for line in path.read_text(encoding='utf-8-sig').splitlines()[:10]:
        if line.startswith('# ck3loc-export: '):
            return line.split(': ', 1)[1].strip()
    return ''


def import_yml(ctx, path: Path, export_id: str | None = None) -> ImportReport:
    report = ImportReport(export_id=file_export_id(path) or export_id or '')
    loc = LocFile.load(path)
    if loc.header_lang != ctx.project['target_lang']:
        report.fatal = 'Wrong localization language'
        return report
    if any(d.severity == 'error' for d in loc.diagnostics()):
        report.fatal = 'Invalid localization file'
        return report
    registered = {r['key']: r for r in ctx.conn.execute('SELECT * FROM export_units WHERE export_id=?', (report.export_id,))}
    if report.export_id and not registered:
        report.fatal = 'Unknown export ID'
        return report
    if not registered:
        report.warnings.append('Source version of this file is unknown; verify it against the current mod')
    seen = set()
    for line in loc.entries():
        key, target = line.key, line.value
        reason = ''
        if key in seen:
            reason = 'Duplicate key'
            report.accepted = [r for r in report.accepted if r.key != key]
        elif key not in ctx.source_values:
            reason = 'Unknown key'
        elif registered and (key not in registered or registered[key]['source_hash'] != semantic_hash(ctx.source_values[key])):
            reason = 'Source changed or key is not in export'
        elif not target.strip():
            reason = 'Empty translation'
        else:
            reason = '; '.join(validate_translation(ctx.source_values[key], target))
        seen.add(key)
        if reason:
            report.rejected.append(RejectedUnit(key, '', reason))
        else:
            report.accepted.append(ImportedUnit(key, target))
    return report


def import_external_xliff(ctx, path: Path) -> ImportReport:
    root = ET.parse(path).getroot()
    report = ImportReport()
    if root.get('trgLang') != lang_code(ctx.project['target_lang']):
        report.fatal = 'Wrong localization language'
        return report
    report.warnings.append('Source version of this file is unknown; verify it against the current mod')
    seen = set()
    for unit in root.iter(f'{{{NS}}}unit'):
        key = unit.get('name') or unit.get('id') or ''
        target = unit.find(f'{{{NS}}}segment/{{{NS}}}target')
        text = ''.join(target.itertext()) if target is not None else ''
        reason = ('Duplicate key' if key in seen else 'Unknown key' if key not in ctx.source_values
                  else 'Empty translation' if not text.strip()
                  else '; '.join(validate_translation(ctx.source_values[key], text)))
        if key in seen:
            report.accepted = [r for r in report.accepted if r.key != key]
        seen.add(key)
        if reason:
            report.rejected.append(RejectedUnit(key, unit.get('id',''), reason))
        else:
            report.accepted.append(ImportedUnit(key,text))
    return report


def import_files(ctx, paths: list[Path], export_id: str | None = None) -> ImportReport:
    result = ImportReport()
    accepted = {}
    conflicts = set()
    for path in paths:
        try:
            suffix = path.suffix.lower()
            report = (import_jsonl(ctx.conn, path, ctx.source_values, export_id) if suffix == '.jsonl'
                      else import_xliff(ctx.conn, path, ctx.source_values) if suffix in {'.xliff', '.xlf'}
                      else import_yml(ctx, path, export_id) if suffix == '.yml' else ImportReport(fatal='Unsupported file'))
            if suffix in {'.xliff','.xlf'} and report.fatal and not ctx.conn.execute(
                'SELECT 1 FROM exports WHERE export_id=?', (report.export_id,)).fetchone():
                report = import_external_xliff(ctx, path)
        except (OSError, ValueError, ET.ParseError) as exc:
            result.warnings.append(f'{path.name}: {exc}')
            continue
        if report.fatal:
            result.warnings.append(f'{path.name}: {report.fatal}')
            continue
        if report.export_id:
            project = ctx.conn.execute('SELECT project_id FROM exports WHERE export_id=?', (report.export_id,)).fetchone()
            if not project or project[0] != ctx.project_id:
                result.warnings.append(f'{path.name}: belongs to another project; use bulk import')
                continue
        result.rejected.extend(report.rejected)
        result.warnings.extend(report.warnings)
        for item in report.accepted:
            previous = accepted.get(item.key)
            if previous and previous.target != item.target:
                conflicts.add(item.key)
            else:
                accepted[item.key] = item
            ids = result.unit_exports.setdefault(item.key, [])
            if report.export_id and report.export_id not in ids:
                ids.append(report.export_id)
            baselines = {r[0] for task in ids for r in ctx.conn.execute(
                'SELECT baseline FROM export_units WHERE export_id=? AND key=?', (task, item.key))}
            if len(baselines) > 1:
                conflicts.add(item.key)
        if report.export_id:
            result.export_id = result.export_id or report.export_id
    for key in conflicts:
        accepted.pop(key, None)
        result.rejected.append(RejectedUnit(key, '', 'Conflicting returned translations; choose one file'))
    result.accepted = list(accepted.values())
    return result


def stage_import(ctx, report: ImportReport, provider: str | None = None) -> str:
    if not report.ok:
        raise ValueError(report.fatal)
    provider = provider or ('external_llm' if report.export_id else 'unknown')
    rows = [{'key': r.key, 'source': ctx.source_values[r.key]} for r in report.accepted]
    job_id = create_job(ctx, rows, provider, options={'export_id': report.export_id,
        'unit_exports': report.unit_exports})
    with ctx.conn:
        for item in report.accepted:
            export_ids = report.unit_exports.get(item.key, [report.export_id] if report.export_id else [])
            for task in export_ids:
                registered = ctx.conn.execute('SELECT baseline FROM export_units WHERE export_id=? AND key=?',
                                              (task, item.key)).fetchone()
                if registered and registered[0]:
                    ctx.conn.execute('UPDATE job_results SET baseline=? WHERE job_id=? AND key=?',
                                     (registered[0], job_id, item.key))
                ctx.conn.execute('INSERT INTO export_returns VALUES (?,?,?) ON CONFLICT(export_id,key) DO UPDATE SET target_text=excluded.target_text',
                                 (task, item.key, item.target))
            item_provider = provider if export_ids else 'unknown'
            stage_result(ctx.conn, job_id, item.key, item.target, item_provider, method='file')
    return job_id


def export_progress(conn, export_id: str) -> tuple[int, int, int]:
    returned = {r[0] for r in conn.execute('SELECT key FROM export_returns WHERE export_id=?', (export_id,))}
    parts = [json.loads(r[0]) for r in conn.execute('SELECT keys_json FROM export_parts WHERE export_id=?', (export_id,))]
    return sum(set(p) <= returned for p in parts), len(parts), sum(len(set(p) - returned) for p in parts)


def result_files(directory: Path) -> list[Path]:
    paths = []
    for root, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(root) / d).is_symlink())
        paths.extend(Path(root) / f for f in sorted(files)
                     if Path(f).suffix.lower() in SUPPORTED | ARCHIVES and not (Path(root) / f).is_symlink())
    return paths


def route_files(conn, paths: list[Path]) -> tuple[dict[int, list[Path]], list[str]]:
    routed, errors = {}, []
    for path in paths:
        try:
            export_id = file_export_id(path)
            row = conn.execute('SELECT project_id FROM exports WHERE export_id=?', (export_id,)).fetchone()
            if not row:
                raise ValueError('Unknown export; select a project or registered task explicitly')
            routed.setdefault(row[0], []).append(path)
        except (OSError, ValueError, ET.ParseError) as exc:
            errors.append(f'{path.name}: {exc}')
    return routed, errors


# ---------- пакет для внешней LLM: ZIP-архивы + один файл с промптом ----------

PACKAGE_PROMPT = """Ты — переводчик модов Crusader Kings 3 с {source_lang} на {target_lang}.
{archives_line}
Внутри архива — папки модов с файлами {format_name}. Каждый файл переводи отдельно.

Правила (обязательные):
{format_rules}
- Маркеры вида ⟦T1⟧, ⟦T2⟧, а также [..], $..$, @..!, #..#! — игровые коды. Переноси их без изменений,
  не переводи, не удаляй и не добавляй свои.
- Литеральную последовательность \\n (обратный слэш + n) сохраняй как есть.
- Термины глоссария (если он указан ниже) переводи строго по нему, с учётом падежей.
- Верни результат ZIP-архивом с теми же папками и именами файлов (можно вернуть и отдельные файлы).
  Ничего не пропускай и не добавляй пояснений внутрь файлов.
{glossary_block}"""

FORMAT_RULES = {
    'jsonl': ('JSONL (одна строка — один JSON-объект)',
              '- Заполни поле "target" переводом поля "source". Поля "export_id", "id", "key", "source", "type",\n'
              '  "tokens", "current_target" не меняй. Поле "current_target" — прежний перевод (если есть), для справки.\n'
              '- Сохрани все строки и их порядок, по одному JSON-объекту на строку.'),
    'xliff': ('XLIFF 2.1',
              '- Заполни элементы <target> переводом <source>. Атрибуты id/name, <source> и метаданные не меняй.'),
    'yml': ('CK3 YML (l_<язык>:)',
            '- Переводи только текст в кавычках. Ключи, номера после двоеточия, заголовок l_<язык>: и строку\n'
            '  комментария "# ck3loc-export: ..." оставь без изменений. Кодировка UTF-8 с BOM.'),
}


@dataclass
class PackageResult:
    archives: list[Path]
    prompt: Path
    rows: int
    sizes: list[int]


def package_name(title: str, target_lang: str) -> str:
    import time
    return f"{_slug(title)}_{target_lang}_{time.strftime('%Y%m%d_%H%M%S')}"


def package_sizes(total: int, archives: int | None = None, rows_per_archive: int | None = None,
                  *, chars_per_archive: int | None = None, lengths: list[int] | None = None) -> list[int]:
    """Размеры архивов: поровну на N архивов, не больше N строк или N символов в архиве.

    Пустых архивов не бывает; при делении по строкам последний архив меньше.
    По объёму (lengths — длина исходника каждой строки по порядку) архив
    закрывается, когда следующая строка превысит лимит; строка длиннее
    лимита уходит в отдельный архив.
    """
    if total <= 0:
        return []
    if chars_per_archive is not None:
        if isinstance(chars_per_archive, bool) or int(chars_per_archive) <= 0:
            raise ValueError('Characters per archive must be a positive integer')
        if lengths is None or len(lengths) != total:
            raise ValueError('Row lengths are required for splitting by text volume')
        limit, sizes, count, volume = int(chars_per_archive), [], 0, 0
        for length in lengths:
            if count and volume + length > limit:
                sizes.append(count)
                count, volume = 0, 0
            count += 1
            volume += length
        sizes.append(count)
        return sizes
    if rows_per_archive is not None:
        if isinstance(rows_per_archive, bool) or int(rows_per_archive) <= 0:
            raise ValueError('Rows per archive must be a positive integer')
        limit = int(rows_per_archive)
        return [min(limit, total - start) for start in range(0, total, limit)]
    if archives is not None and (isinstance(archives, bool) or int(archives) <= 0):
        raise ValueError('Archive count must be a positive integer')
    count = max(1, min(int(archives or 1), total))
    return [total // count + (1 if i < total % count else 0) for i in range(count)]


def split_preview(row_groups, **split) -> list[int]:
    """Размеры архивов для предпросмотра: row_groups — строки проектов в порядке выгрузки."""
    rows = [r for group in row_groups for r in group]
    if split.get('chars_per_archive') is not None:
        return package_sizes(len(rows), chars_per_archive=split['chars_per_archive'],
                             lengths=[len(r['source']) for r in rows])
    return package_sizes(len(rows), split.get('archives'), split.get('rows_per_archive'))


def describe_sizes(sizes: list[int]) -> str:
    """Коротко: «28 × 250», «27 × 250 + 130», «3 × 1400 + 2 × 1399»."""
    groups: list[list[int]] = []
    for size in sizes:
        if groups and groups[-1][1] == size:
            groups[-1][0] += 1
        else:
            groups.append([1, size])
    return ' + '.join(f'{count} × {size}' if count > 1 else str(size) for count, size in groups) or '0'


def _slug(text: str) -> str:
    import re
    cleaned = re.sub(r'[^\w\-]+', '_', text, flags=re.UNICODE).strip('_')
    return (cleaned or 'mod')[:60]


def write_package(items: list[tuple], out_dir: Path, fmt: str = 'jsonl', archives: int | None = None,
                  name: str = 'ck3loc_task', *, rows_per_archive: int | None = None,
                  chars_per_archive: int | None = None) -> PackageResult:
    """items: [(ctx, rows)] — строки rows_to_translate каждого проекта.

    Создаёт name.zip (или name_1_of_N.zip …) и рядом name_PROMPT.txt. Каждый
    фрагмент проекта регистрируется как отдельная выгрузка (export_id), поэтому
    загрузка возвращённых файлов сопоставляет их по заданию, а не по имени.
    """
    import tempfile
    import zipfile

    if fmt not in FORMATS:
        raise ValueError('Unsupported export format')
    items = [(ctx, rows) for ctx, rows in items if rows]
    total = sum(len(rows) for _ctx, rows in items)
    lengths = [len(r['source']) for _ctx, rows in items for r in rows] if chars_per_archive is not None else None
    sizes = package_sizes(total, archives, rows_per_archive, chars_per_archive=chars_per_archive, lengths=lengths)
    if not sizes:
        raise ValueError('Nothing to export')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = len(sizes)
    names = [f'{name}.zip'] if count == 1 else [f'{name}_{i}_of_{count}.zip' for i in range(1, count + 1)]
    archive_paths = [out_dir / n for n in names]
    prompt_path = out_dir / f'{name}_PROMPT.txt'
    if any(p.exists() for p in archive_paths + [prompt_path]):
        raise FileExistsError('Export destination already contains these files')

    # Раскладка: проекты идут подряд и делятся между архивами поровну по строкам.
    segments: list[list[tuple]] = [[] for _ in sizes]
    archive, room = 0, sizes[0]
    for ctx, rows in items:
        start = 0
        while start < len(rows):
            take = min(room, len(rows) - start)
            segments[archive].append((ctx, rows[start:start + take]))
            start += take
            room -= take
            if room == 0 and archive + 1 < count:
                archive += 1
                room = sizes[archive]

    glossary_terms: dict[str, str] = {}
    texts = []
    pairs = set()
    written = []
    try:
        with tempfile.TemporaryDirectory(prefix='ck3loc_pkg_') as temporary:
            temp = Path(temporary)
            for index, segment in enumerate(segments):
                with zipfile.ZipFile(archive_paths[index], 'w', zipfile.ZIP_DEFLATED) as zf:
                    written.append(archive_paths[index])
                    for number, (ctx, rows) in enumerate(segment, 1):
                        folder = f"{_slug(ctx.scan.name)}_{ctx.project_id}"
                        root = temp / f'a{index}' / f'{folder}_{number}'
                        plan = plan_export(ctx, root, fmt, 'selected', {r['key'] for r in rows}, None)
                        write_export(ctx, plan)
                        ctx.conn.execute('INSERT INTO export_packages VALUES (?,?,?)',
                                         (name, index + 1, plan.export_id))
                        ctx.conn.commit()
                        for part in plan.parts:
                            if fmt == 'yml':
                                inner = part.path.relative_to(root).as_posix()
                            else:
                                inner = f'{folder}_part{index + 1}{part.path.suffix}'
                            zf.write(part.path, f'{folder}/{inner}')
                        pairs.add((ctx.project['source_lang'], ctx.project['target_lang']))
                        texts.extend(r['source'] for r in rows)
                        for s, t in load_glossary(ctx.conn, ctx.project['mod_id'], ctx.project['source_lang'],
                                                  ctx.project['target_lang']):
                            glossary_terms.setdefault(s, t)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    relevant = relevant_glossary(sorted(glossary_terms.items()), texts, limit=120, max_chars=9000)
    source = ', '.join(sorted({s for s, _t in pairs}))
    target = ', '.join(sorted({t for _s, t in pairs}))
    archives_line = (f'Приложен ZIP-архив {names[0]}.' if count == 1 else
                     f'Задание разделено на {count} ZIP-архивов ({names[0]} … {names[-1]}); '
                     'обрабатывай их по одному, правила одинаковые.')
    format_name, format_rules = FORMAT_RULES[fmt]
    glossary_block = ('\nГлоссарий:\n' + '\n'.join(f'  {s} → {t}' for s, t in relevant) + '\n') if relevant else ''
    prompt_path.write_text(PACKAGE_PROMPT.format(source_lang=source, target_lang=target, archives_line=archives_line,
                                                 format_name=format_name, format_rules=format_rules,
                                                 glossary_block=glossary_block), encoding='utf-8')
    return PackageResult(archive_paths, prompt_path, total, sizes)


def package_progress(conn, export_ids) -> list[tuple[str, int, int, int]]:
    """(пакет, вернувшихся архивов, всего архивов, строк ещё не вернулось)."""
    packages = sorted({r[0] for e in export_ids for r in conn.execute(
        'SELECT package FROM export_packages WHERE export_id=?', (e,))})
    result = []
    for package in packages:
        archives: dict[int, list[str]] = {}
        for archive, export_id in conn.execute(
                'SELECT archive, export_id FROM export_packages WHERE package=?', (package,)):
            archives.setdefault(archive, []).append(export_id)
        received, missing = 0, 0
        for ids in archives.values():
            lost = sum(export_progress(conn, e)[2] for e in ids)
            missing += lost
            received += lost == 0
        result.append((package, received, len(archives), missing))
    return result


MAX_UNPACKED_BYTES = 512 * 1024 * 1024


def expand_archives(paths: list[Path], temp_dir: Path) -> tuple[list[Path], list[str]]:
    """Распаковать возвращённые ZIP (только поддерживаемые файлы, без выхода за папку)."""
    import zipfile

    result, errors = [], []
    for number, path in enumerate(paths):
        path = Path(path)
        if path.suffix.lower() != '.zip':
            result.append(path)
            continue
        try:
            with zipfile.ZipFile(path) as zf:
                total = 0
                target_root = Path(temp_dir) / f'{number}_{_slug(path.stem)}'
                for info in zf.infolist():
                    inner = Path(info.filename)
                    if info.is_dir() or inner.suffix.lower() not in SUPPORTED:
                        continue
                    if inner.is_absolute() or '..' in inner.parts or ':' in info.filename:
                        errors.append(f'{path.name}: {info.filename}: unsafe path')
                        continue
                    total += info.file_size
                    if total > MAX_UNPACKED_BYTES:
                        raise ValueError('Archive is too large')
                    destination = target_root / inner
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(zf.read(info))
                    result.append(destination)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            errors.append(f'{path.name}: {exc}')
    return result, errors
