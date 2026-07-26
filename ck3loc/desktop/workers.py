"""Фоновые задачи GUI: сканирование, перевод, пакетный режим, запись.

Каждый воркер открывает собственное подключение к базе — SQLite-соединения
нельзя делить между потоками.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ck3loc.core.i18n import tr, tr_format


@dataclass
class ModRow:
    mod_id: str
    name: str
    n_langs: int
    coverage: float | None
    state: str
    has_loc: bool
    updated: str = ""
    errors: int = 0
    tracked: bool = False
    provider_name: str = ""      # мод-русификатор, покрывающий этот мод
    translates: int = 0          # сам является русификатором для N модов
    source_keys: int = 0
    updated_ts: int = 0          # для сортировки по дате обновления


class ScanWorker(QThread):
    """Скан библиотеки: моды, языки, покрытие, снимки, уведомления."""

    progress = Signal(int, int, str)
    note = Signal(str)
    finished_rows = Signal(list)

    def __init__(self, source_lang="english", target_lang="russian",
                 steam_path: str = ""):
        super().__init__()
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.steam_path = steam_path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import datetime

        from ck3loc.core import db
        from ck3loc.core.scanner import scan_mod
        from ck3loc.core.steam import (
            find_steam_root,
            list_workshop_mod_dirs,
            read_workshop_acf,
            workshop_content_dirs,
        )
        from ck3loc.core.store import (
            diff_snapshots,
            latest_snapshot,
            mark_missing_mods,
            record_mod,
            take_snapshot,
        )
        from ck3loc.core.vanilla import game_languages

        conn = db.connect()
        try:
            root = find_steam_root(Path(self.steam_path) if self.steam_path else None)
            if root is None:
                self.note.emit(
                    "Steam не найден. Укажите путь в Настройках."
                )
                self.finished_rows.emit([])
                return
            content = workshop_content_dirs(root)
            if not content:
                self.note.emit(
                    "Папка мастерской CK3 не найдена в библиотеках Steam."
                )
                self.finished_rows.emit([])
                return
            mod_dirs = list_workshop_mod_dirs(content)
            langs = game_languages()
            acf = read_workshop_acf(root)
            tracked = {
                r["mod_id"]
                for r in conn.execute(
                    "SELECT DISTINCT mod_id FROM translation_projects"
                ).fetchall()
            }
            rows: list[ModRow] = []
            total = len(mod_dirs)
            for i, mod_dir in enumerate(mod_dirs, start=1):
                if self._stop:
                    break
                scan = scan_mod(mod_dir, langs)
                self.progress.emit(i, total, scan.name)
                entry = acf.get(scan.mod_id)
                t_upd = int(entry.time_updated) if entry and entry.time_updated else 0
                record_mod(conn, scan, steam_time_updated=t_upd)
                updated = (
                    f"{datetime.datetime.fromtimestamp(t_upd):%d.%m.%Y}"
                    if t_upd else ""
                )
                errors = sum(
                    1 for _p, d in scan.diagnostics if d.severity == "error"
                )
                if not scan.has_localization:
                    rows.append(ModRow(scan.mod_id, scan.name, 0, None,
                                       tr("нет локализации"), False, updated,
                                       errors, scan.mod_id in tracked,
                                       updated_ts=t_upd))
                    continue
                prev = latest_snapshot(conn, scan.mod_id)
                snap = take_snapshot(conn, scan, steam_time_updated=t_upd)
                if snap.is_new and prev is not None:
                    self._report_changes(conn, scan, prev["id"], snap.snapshot_id)
                src = scan.best_source_language(self.source_lang) or self.source_lang
                translated, of = scan.coverage(self.target_lang, src)
                if of == 0:
                    state = tr_format("нет языка {lang}", lang=src)
                    cov = None
                elif translated == 0:
                    state, cov = tr("нет перевода"), 0.0
                elif translated < of:
                    state = tr_format("{n} пропущено", n=of - translated)
                    cov = 100.0 * translated / of
                else:
                    state, cov = tr("полный"), 100.0
                rows.append(ModRow(scan.mod_id, scan.name, len(scan.languages),
                                   cov, state, True, updated, errors,
                                   scan.mod_id in tracked, source_keys=of,
                                   updated_ts=t_upd))
            gone = mark_missing_mods(conn, {d.name for d in mod_dirs})
            for g in gone:
                self.note.emit(
                    f"Мод {g} больше не установлен — перевод и история "
                    f"сохранены в базе."
                )
            self._detect_providers(conn, rows)
            self.finished_rows.emit(rows)
        except Exception as e:  # noqa: BLE001
            self.note.emit(f"Ошибка сканирования: {e}")
            self.finished_rows.emit([])
        finally:
            conn.close()

    def _detect_providers(self, conn, rows: list[ModRow]):
        """Найти моды-русификаторы и пересчитать покрытие модов, которые
        они переводят."""
        from ck3loc.core import settings
        from ck3loc.core.external_translations import (
            find_provider_candidates,
            providers_index,
            provider_roles,
            save_candidates,
        )

        cfg = settings.load()
        if not cfg.get("provider_detect", True):
            return
        self.progress.emit(0, 1, "Ищу моды-русификаторы…")
        candidates = find_provider_candidates(
            conn, self.source_lang, self.target_lang,
            min_ratio=float(cfg.get("provider_min_ratio", 0.25)),
            min_keys=int(cfg.get("provider_min_keys", 30)),
        )
        save_candidates(conn, self.target_lang, candidates)
        index = providers_index(conn, self.target_lang)
        roles = provider_roles(conn, self.target_lang)
        if not index:
            return
        names = {r.mod_id: r.name for r in rows}
        by_id = {r.mod_id: r for r in rows}
        for mod_id, provider_id in index.items():
            row = by_id.get(mod_id)
            if row is None:
                continue
            row.provider_name = names.get(provider_id, provider_id)
            best = candidates.get(mod_id, [])
            covered = best[0].covered_keys if best else 0
            total = best[0].source_keys if best else row.source_keys
            if total:
                row.coverage = min(100.0, 100.0 * covered / total)
                left = max(0, total - covered)
                row.state = (
                    tr("переведён другим модом") if left == 0
                    else tr_format("чужой перевод, {n} пропущено", n=left)
                )
        for provider_id, targets in roles.items():
            row = by_id.get(provider_id)
            if row is not None:
                row.translates = len(targets)
                row.state = (
                    tr_format("русификатор для «{name}»",
                              name=names.get(targets[0], targets[0]))
                    if len(targets) == 1
                    else tr_format("русификатор для {n} модов", n=len(targets))
                )
                row.coverage = None
        self.note.emit(
            f"Найдено модов-русификаторов: {len(roles)}; они покрывают "
            f"{len(index)} модов."
        )

    def _report_changes(self, conn, scan, old_id: int, new_id: int):
        from ck3loc.core.store import diff_snapshots

        parts = []
        for lang in scan.languages:
            d = diff_snapshots(conn, old_id, new_id, lang)
            if not d.empty:
                parts.append(
                    f"{lang}: +{len(d.added)} ~{len(d.changed)} −{len(d.removed)}"
                )
        if parts:
            self.note.emit(
                f"«{scan.name}» обновился, локализация изменилась — "
                + "; ".join(parts)
            )


class TranslateWorker(QThread):
    """Перевод одного мода выбранным провайдером."""

    progress = Signal(int, int)
    line = Signal(str)
    done = Signal(object)

    def __init__(self, mod_id: str, provider_name: str, what: str,
                 source_lang: str, target_lang: str):
        super().__init__()
        self.mod_id = mod_id
        self.provider_name = provider_name
        self.what = what
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run(self):
        from ck3loc.core import db
        from ck3loc.core.glossary_seed import seed_glossary
        from ck3loc.core.ops import load_project_context, rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, translate_rows
        from ck3loc.providers.registry import make_provider

        conn = db.connect()
        try:
            seed_glossary(conn)
            ctx = load_project_context(conn, self.mod_id, self.source_lang,
                                       self.target_lang)
            if ctx is None:
                self.line.emit("Мод не найден.")
                self.done.emit(None)
                return
            rows = rows_to_translate(ctx, self.what)
            if not rows:
                self.line.emit("Переводить нечего — всё актуально.")
                self.done.emit(None)
                return
            provider = make_provider(self.provider_name)
            vl = build_vanilla_lookup(ctx.project["source_lang"],
                                      ctx.project["target_lang"])
            stats = translate_rows(
                ctx, rows, provider,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                vanilla_lookup=vl,
            )
            self.done.emit(stats)
        except Exception as e:  # noqa: BLE001
            self.line.emit(f"Ошибка: {e}")
            self.done.emit(None)
        finally:
            conn.close()


class BatchWorker(QThread):
    """Пакетный перевод всех модов без целевого языка + запись."""

    progress = Signal(int, int)
    line = Signal(str)
    done = Signal()

    def __init__(self, provider_name: str, source_lang: str, target_lang: str,
                 write_after: bool = True, limit: int = 0):
        super().__init__()
        self.provider_name = provider_name
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.write_after = write_after
        self.limit = limit
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from ck3loc.core import db
        from ck3loc.core.glossary_seed import seed_glossary
        from ck3loc.core.ops import load_project_context, rows_to_translate
        from ck3loc.core.pipeline import build_vanilla_lookup, translate_rows
        from ck3loc.core.scanner import scan_mod
        from ck3loc.core.steam import list_workshop_mod_dirs, workshop_content_dirs
        from ck3loc.core.vanilla import game_languages
        from ck3loc.core.writer import apply_write_plan, build_write_plan
        from ck3loc.providers.registry import make_provider

        conn = db.connect()
        try:
            seed_glossary(conn)
            provider = make_provider(self.provider_name)
            langs = game_languages()
            queue = []
            for mod_dir in list_workshop_mod_dirs(workshop_content_dirs()):
                scan = scan_mod(mod_dir, langs)
                if not scan.has_localization:
                    continue
                src = scan.best_source_language(self.source_lang) or self.source_lang
                translated, of = scan.coverage(self.target_lang, src)
                if of > 0 and translated == 0:
                    queue.append(mod_dir)
            if self.limit:
                queue = queue[: self.limit]
            self.line.emit(f"Модов без перевода: {len(queue)}")
            vl = build_vanilla_lookup(self.source_lang, self.target_lang)
            for i, mod_dir in enumerate(queue, start=1):
                if self._stop:
                    self.line.emit("Остановлено пользователем.")
                    break
                self.progress.emit(i, len(queue))
                ctx = load_project_context(conn, mod_dir.name, self.source_lang,
                                           self.target_lang, mod_dir=mod_dir)
                rows = rows_to_translate(ctx, "missing")
                self.line.emit(f"[{i}/{len(queue)}] {ctx.scan.name}: {len(rows)} строк")
                stats = translate_rows(ctx, rows, provider, vanilla_lookup=vl)
                self.line.emit(
                    f"     ваниль {stats.from_vanilla} · память {stats.from_memory} "
                    f"· API {stats.from_api} · ошибок {len(stats.failed)}"
                )
                if self.write_after:
                    ctx = load_project_context(conn, mod_dir.name, self.source_lang,
                                               self.target_lang, mod_dir=mod_dir)
                    plan = build_write_plan(ctx.scan, ctx.project, ctx.units)
                    if plan.total_keys:
                        apply_write_plan(conn, ctx.project_id, plan, ctx.scan,
                                         ctx.units)
                        self.line.emit(f"     записано ключей: {plan.total_keys}")
            self.done.emit()
        except Exception as e:  # noqa: BLE001
            self.line.emit(f"Ошибка: {e}")
            self.done.emit()
        finally:
            conn.close()
