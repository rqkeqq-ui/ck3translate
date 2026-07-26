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

    @property
    def ratio(self) -> float:
        return self.covered_keys / self.source_keys if self.source_keys else 0.0

    @property
    def confidence(self) -> str:
        if self.by_dependency or self.ratio >= 0.8:
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

    candidates = [
        mod_id for mod_id, langs in lang_counts.items()
        if langs.get(target_lang, 0) >= min_keys and not langs.get(source_lang)
    ]
    if not candidates:
        return {}

    provider_keys = {
        mod_id: _keys(conn, snaps[mod_id], target_lang) for mod_id in candidates
    }
    # имена оригиналов, объявленные в dependencies
    provider_deps = {
        mod_id: {d.strip().lower() for d in read_dependencies(Path(dirs.get(mod_id, "")))}
        for mod_id in candidates
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
        for provider_id in candidates:
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
        if found:
            found.sort(key=lambda c: (c.by_dependency, c.covered_keys), reverse=True)
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
