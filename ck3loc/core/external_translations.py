"""Обнаружение модов-русификаторов (переводов, живущих отдельным модом).

Основной сигнал — пересечение ключей: мод-поставщик содержит целевой язык
и покрывает ключи мода-оригинала. На реальной библиотеке разрыв между
настоящим поставщиком и случайным пересечением большой (98% против 17%),
поэтому порог работает уверенно.

Подтверждающие сигналы (для подписи и уверенности, не для поиска):
  * dependencies в descriptor.mod с именем оригинала;
  * в моде есть только целевой язык и нет исходного;
  * в названии «русификатор», «translation», имя оригинала.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MIN_RATIO = 0.25
DEFAULT_MIN_KEYS = 30

_NAME_MARKERS = (
    "русифик", "русский перевод", "перевод", "локализац",
    "translation", "localisation", "localization", "ru loc",
)

_DEP_RE = re.compile(r"dependencies\s*=\s*\{(.*?)\}", re.S | re.I)
_QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def read_dependencies(mod_dir: Path) -> list[str]:
    """Имена модов из блока dependencies={...} в descriptor.mod."""
    p = Path(mod_dir) / "descriptor.mod"
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    m = _DEP_RE.search(text)
    if not m:
        return []
    return [d.replace('\\"', '"') for d in _QUOTED_RE.findall(m.group(1))]


def looks_like_translation_name(name: str) -> bool:
    low = (name or "").lower()
    return any(marker in low for marker in _NAME_MARKERS)


@dataclass
class ProviderCandidate:
    """Мод, который переводит другой мод."""

    provider_id: str
    provider_name: str
    covered_keys: int
    source_keys: int
    by_dependency: bool = False
    by_name: bool = False
    by_registry: bool = False

    @property
    def ratio(self) -> float:
        return self.covered_keys / self.source_keys if self.source_keys else 0.0

    @property
    def confidence(self) -> str:
        if self.by_registry or self.by_dependency or self.ratio >= 0.8:
            return "высокая"
        if self.ratio >= 0.5 or self.by_name:
            return "средняя"
        return "низкая"


def _latest_snapshots(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT mod_id, MAX(id) AS sid FROM mod_snapshots GROUP BY mod_id"
    ).fetchall()
    return {r["mod_id"]: r["sid"] for r in rows}


def _keys(conn: sqlite3.Connection, snapshot_id: int, language: str) -> set[str]:
    return {
        r["key"]
        for r in conn.execute(
            "SELECT key FROM snapshot_entries WHERE snapshot_id=? AND language=?",
            (snapshot_id, language),
        )
    }


def find_provider_candidates(
    conn: sqlite3.Connection,
    source_lang: str,
    target_lang: str,
    min_ratio: float = DEFAULT_MIN_RATIO,
    min_keys: int = DEFAULT_MIN_KEYS,
    progress_cb=None,
    only_mod_id: str | None = None,
    registered_pairs=(),
) -> dict[str, list[ProviderCandidate]]:
    """Для каждого мода — список модов, которые его переводят.

    Кандидатами в поставщики считаются моды, где есть целевой язык и нет
    исходного: именно так устроены отдельные моды-русификаторы.
    """
    snaps = _latest_snapshots(conn)
    if not snaps:
        return {}

    names = {
        r["mod_id"]: (r["name"] or r["workshop_title"] or r["mod_id"])
        for r in conn.execute("SELECT mod_id, name, workshop_title FROM mods")
    }
    dirs = {
        r["mod_id"]: r["mod_dir"]
        for r in conn.execute("SELECT mod_id, mod_dir FROM mods")
    }

    # какие языки есть у каждого мода
    lang_counts: dict[str, dict[str, int]] = {}
    for mod_id, sid in snaps.items():
        rows = conn.execute(
            """SELECT language, COUNT(*) AS n FROM snapshot_entries
               WHERE snapshot_id=? GROUP BY language""",
            (sid,),
        ).fetchall()
        lang_counts[mod_id] = {r["language"]: r["n"] for r in rows}

    auto_candidates = [
        mod_id for mod_id, langs in lang_counts.items()
        if langs.get(target_lang, 0) >= min_keys and not langs.get(source_lang)
    ]

    def pair_value(pair, name: str) -> str:
        if isinstance(pair, dict):
            return str(pair.get(name, ""))
        return str(getattr(pair, name, ""))

    registered = [
        pair for pair in registered_pairs
        if pair_value(pair, "source_lang") == source_lang
        and pair_value(pair, "target_lang") == target_lang
        and pair_value(pair, "source_mod_id") in snaps
        and pair_value(pair, "provider_mod_id") in snaps
    ]
    registered_provider_ids = {
        pair_value(pair, "provider_mod_id") for pair in registered
    }
    provider_ids = set(auto_candidates) | registered_provider_ids

    provider_keys = {
        mod_id: _keys(conn, snaps[mod_id], target_lang) for mod_id in provider_ids
    }
    # имена оригиналов, объявленные в dependencies
    provider_deps = {
        mod_id: {d.strip().lower() for d in read_dependencies(Path(dirs.get(mod_id, "")))}
        for mod_id in auto_candidates
    }

    result: dict[str, list[ProviderCandidate]] = {}
    targets = [
        mod_id for mod_id, langs in lang_counts.items()
        if langs.get(source_lang, 0) > 0
        and (only_mod_id is None or mod_id == only_mod_id)
    ]
    for i, mod_id in enumerate(targets, start=1):
        if progress_cb:
            progress_cb(i, len(targets))
        src_keys = _keys(conn, snaps[mod_id], source_lang)
        if not src_keys:
            continue
        mod_name = (names.get(mod_id) or "").strip().lower()
        found: list[ProviderCandidate] = []
        for provider_id in auto_candidates:
            if provider_id == mod_id:
                continue
            covered = len(src_keys & provider_keys[provider_id])
            if covered < min_keys:
                continue
            ratio = covered / len(src_keys)
            by_dep = mod_name in provider_deps[provider_id] if mod_name else False
            if ratio < min_ratio and not by_dep:
                continue
            found.append(
                ProviderCandidate(
                    provider_id=provider_id,
                    provider_name=names.get(provider_id, provider_id),
                    covered_keys=covered,
                    source_keys=len(src_keys),
                    by_dependency=by_dep,
                    by_name=looks_like_translation_name(
                        names.get(provider_id, "")
                    ),
                )
            )
        # Запись сообщества снимает эвристические пороги, но не подменяет
        # факты: оба мода должны быть установлены и реально иметь общие ключи.
        for pair in registered:
            if pair_value(pair, "source_mod_id") != mod_id:
                continue
            provider_id = pair_value(pair, "provider_mod_id")
            if provider_id == mod_id:
                continue
            covered = len(src_keys & provider_keys.get(provider_id, set()))
            if covered == 0:
                continue
            existing = next(
                (item for item in found if item.provider_id == provider_id), None
            )
            if existing is not None:
                existing.by_registry = True
                continue
            found.append(
                ProviderCandidate(
                    provider_id=provider_id,
                    provider_name=names.get(provider_id, provider_id),
                    covered_keys=covered,
                    source_keys=len(src_keys),
                    by_name=looks_like_translation_name(
                        names.get(provider_id, "")
                    ),
                    by_registry=True,
                )
            )
        if found:
            found.sort(
                key=lambda c: (
                    c.by_registry, c.by_dependency, c.covered_keys
                ),
                reverse=True,
            )
            result[mod_id] = found
    return result


# ---------- хранение результата ----------

def save_candidates(
    conn: sqlite3.Connection,
    target_lang: str,
    candidates: dict[str, list[ProviderCandidate]],
) -> None:
    """Записать найденных поставщиков, сохранив ручной выбор пользователя."""
    manual = {
        r["mod_id"]: r["provider_mod_id"]
        for r in conn.execute(
            """SELECT mod_id, provider_mod_id FROM translation_providers
               WHERE target_lang=? AND chosen_manually=1""",
            (target_lang,),
        )
    }
    disabled = {
        r["mod_id"]
        for r in conn.execute(
            """SELECT mod_id FROM translation_providers
               WHERE target_lang=? AND chosen_manually=1
                 AND provider_mod_id='' """,
            (target_lang,),
        )
    }
    conn.execute(
        "DELETE FROM translation_providers WHERE target_lang=? AND chosen_manually=0",
        (target_lang,),
    )
    for mod_id, items in candidates.items():
        if mod_id in manual or mod_id in disabled:
            continue
        best = items[0]
        conn.execute(
            """INSERT INTO translation_providers
                   (mod_id, target_lang, provider_mod_id, covered_keys,
                    source_keys, chosen_manually)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (mod_id, target_lang, best.provider_id, best.covered_keys,
             best.source_keys),
        )
    conn.commit()


def set_manual_choice(
    conn: sqlite3.Connection, mod_id: str, target_lang: str,
    provider_id: str, covered: int = 0, source_keys: int = 0,
) -> None:
    """Зафиксировать выбор пользователя (пустой provider_id — не учитывать)."""
    conn.execute(
        "DELETE FROM translation_providers WHERE mod_id=? AND target_lang=?",
        (mod_id, target_lang),
    )
    conn.execute(
        """INSERT INTO translation_providers
               (mod_id, target_lang, provider_mod_id, covered_keys,
                source_keys, chosen_manually)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (mod_id, target_lang, provider_id, covered, source_keys),
    )
    conn.commit()


def get_provider(
    conn: sqlite3.Connection, mod_id: str, target_lang: str
) -> sqlite3.Row | None:
    row = conn.execute(
        """SELECT * FROM translation_providers
           WHERE mod_id=? AND target_lang=?""",
        (mod_id, target_lang),
    ).fetchone()
    if row is None or not row["provider_mod_id"]:
        return None
    return row


def provider_keys_for(
    conn: sqlite3.Connection, mod_id: str, target_lang: str
) -> set[str]:
    """Ключи, которые за нас уже перевёл сторонний мод."""
    row = get_provider(conn, mod_id, target_lang)
    if row is None:
        return set()
    snaps = _latest_snapshots(conn)
    sid = snaps.get(row["provider_mod_id"])
    if sid is None:
        return set()
    return _keys(conn, sid, target_lang)


@dataclass
class Coverage:
    """Сколько строк мода переведено с учётом всех источников."""

    total: int = 0            # ключей в исходном языке
    own: int = 0              # перевёл сам мод
    external_new: int = 0     # добавил мод-русификатор сверх своего перевода
    external_total: int = 0   # всего покрывает русификатор (в т.ч. дубли)

    @property
    def translated(self) -> int:
        return self.own + self.external_new

    @property
    def missing(self) -> int:
        return max(0, self.total - self.translated)

    @property
    def percent(self) -> float | None:
        return None if not self.total else 100.0 * self.translated / self.total


def effective_coverage(
    conn: sqlite3.Connection,
    mod_id: str,
    source_lang: str,
    target_lang: str,
) -> Coverage:
    """Покрытие мода: свой перевод плюс то, что добавляет русификатор.

    Считать только по русификатору нельзя: у мода может быть и свой
    перевод, и тогда доля русификатора занижает картину.
    """
    snaps = _latest_snapshots(conn)
    sid = snaps.get(mod_id)
    if sid is None:
        return Coverage()
    src = _keys(conn, sid, source_lang)
    if not src:
        return Coverage()
    own = _keys(conn, sid, target_lang) & src
    cov = Coverage(total=len(src), own=len(own))
    row = get_provider(conn, mod_id, target_lang)
    if row is not None:
        psid = snaps.get(row["provider_mod_id"])
        if psid is not None:
            ext = _keys(conn, psid, target_lang) & src
            cov.external_total = len(ext)
            cov.external_new = len(ext - own)
    return cov


def native_stale_keys(
    conn: sqlite3.Connection,
    mod_id: str,
    source_lang: str,
    target_lang: str,
) -> set[str]:
    """Ключи, где перевод самого мода отстал от исходного текста.

    Своего отпечатка у чужого перевода нет, поэтому смотрим историю
    снимков: исходная строка менялась позже, чем перевод, — значит,
    перевод устарел. Отсчёт возможен только с первого снимка.
    """
    snaps = [
        r["id"] for r in conn.execute(
            "SELECT id FROM mod_snapshots WHERE mod_id=? ORDER BY id",
            (mod_id,),
        )
    ]
    if len(snaps) < 2:
        return set()
    last_src_change: dict[str, int] = {}
    last_tgt_change: dict[str, int] = {}
    prev_src: dict[str, str] = {}
    prev_tgt: dict[str, str] = {}
    for i, sid in enumerate(snaps):
        src = {
            r["key"]: r["value_hash"] for r in conn.execute(
                """SELECT key, value_hash FROM snapshot_entries
                   WHERE snapshot_id=? AND language=?""", (sid, source_lang))
        }
        tgt = {
            r["key"]: r["value_hash"] for r in conn.execute(
                """SELECT key, value_hash FROM snapshot_entries
                   WHERE snapshot_id=? AND language=?""", (sid, target_lang))
        }
        for key, h in src.items():
            if prev_src.get(key) != h:
                last_src_change[key] = i
        for key, h in tgt.items():
            if prev_tgt.get(key) != h:
                last_tgt_change[key] = i
        prev_src, prev_tgt = src, tgt
    return {
        key for key in prev_tgt
        if key in prev_src
        and last_src_change.get(key, 0) > last_tgt_change.get(key, 0)
    }


@dataclass
class Breakdown:
    """Из чего складывается перевод мода. Части не пересекаются."""

    total: int = 0        # ключей в исходном языке
    own: int = 0          # перевёл автор мода
    external: int = 0     # добавил мод-русификатор сверх авторского
    mine: int = 0         # перевели вы в этой программе
    stale: int = 0        # переведено, но исходный текст с тех пор изменился
    provider_total: int = 0   # сколько всего покрывает русификатор

    @property
    def translated(self) -> int:
        """Устаревшие строки в игре видны, поэтому считаются переведёнными."""
        return self.own + self.external + self.mine + self.stale

    @property
    def missing(self) -> int:
        return max(0, self.total - self.translated)

    @property
    def percent(self) -> float | None:
        return None if not self.total else 100.0 * self.translated / self.total

    def segments(self) -> list[tuple[str, int]]:
        """[(вид, количество)] для полоски — в порядке отрисовки."""
        return [
            ("own", self.own),
            ("external", self.external),
            ("mine", self.mine),
            ("stale", self.stale),
            ("missing", self.missing),
        ]


def coverage_breakdown(
    conn: sqlite3.Connection,
    mod_id: str,
    source_lang: str,
    target_lang: str,
) -> Breakdown:
    """Разложить перевод мода по источникам.

    Приоритет ключа: ваш перевод → русификатор → автор мода → не хватает.
    """
    from .scanner import semantic_hash

    snaps = _latest_snapshots(conn)
    sid = snaps.get(mod_id)
    if sid is None:
        return Breakdown()
    src_rows = {
        r["key"]: r["value"] for r in conn.execute(
            """SELECT key, value FROM snapshot_entries
               WHERE snapshot_id=? AND language=?""", (sid, source_lang))
    }
    if not src_rows:
        return Breakdown()
    src = set(src_rows)
    native = _keys(conn, sid, target_lang) & src

    # наши переводы из базы
    project = conn.execute(
        """SELECT id FROM translation_projects
           WHERE mod_id=? AND source_lang=? AND target_lang=?""",
        (mod_id, source_lang, target_lang),
    ).fetchone()
    mine: set[str] = set()
    mine_stale: set[str] = set()
    if project is not None:
        for r in conn.execute(
            """SELECT key, source_hash, target_text FROM translation_units
               WHERE project_id=?""", (project["id"],)
        ):
            key = r["key"]
            if key not in src or not (r["target_text"] or ""):
                continue
            if r["source_hash"] and r["source_hash"] != semantic_hash(src_rows[key]):
                mine_stale.add(key)
            else:
                mine.add(key)

    # мод-русификатор
    external: set[str] = set()
    provider_total = 0
    row = get_provider(conn, mod_id, target_lang)
    if row is not None:
        psid = snaps.get(row["provider_mod_id"])
        if psid is not None:
            ext_keys = _keys(conn, psid, target_lang) & src
            provider_total = len(ext_keys)
            external = ext_keys - native - mine - mine_stale

    # устаревший перевод самого мода
    native_stale = native_stale_keys(conn, mod_id, source_lang, target_lang)
    native_stale &= native - mine - mine_stale - external

    own = native - mine - mine_stale - external - native_stale
    return Breakdown(
        total=len(src),
        own=len(own),
        external=len(external),
        mine=len(mine),
        stale=len(mine_stale) + len(native_stale),
        provider_total=provider_total,
    )


def providers_index(
    conn: sqlite3.Connection, target_lang: str
) -> dict[str, str]:
    """mod_id → provider_mod_id для быстрой пометки списка модов."""
    return {
        r["mod_id"]: r["provider_mod_id"]
        for r in conn.execute(
            """SELECT mod_id, provider_mod_id FROM translation_providers
               WHERE target_lang=? AND provider_mod_id != ''""",
            (target_lang,),
        )
    }


def provider_roles(conn: sqlite3.Connection, target_lang: str) -> dict[str, list[str]]:
    """provider_mod_id → какие моды он переводит (для пометки в библиотеке)."""
    out: dict[str, list[str]] = {}
    for r in conn.execute(
        """SELECT mod_id, provider_mod_id FROM translation_providers
           WHERE target_lang=? AND provider_mod_id != ''""",
        (target_lang,),
    ):
        out.setdefault(r["provider_mod_id"], []).append(r["mod_id"])
    return out
