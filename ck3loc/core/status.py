"""Автомат статусов строки перевода (раздел 7 спецификации).

Трёхстороннее сравнение: BASE (источник на момент перевода, хранится
в translation_units.source_hash) × текущий источник × текущий перевод.
"""

from __future__ import annotations

from dataclasses import dataclass

from .scanner import semantic_hash

# Итоговые статусы отображения
MISSING = "missing"            # не переведено
MACHINE = "machine"            # машинный перевод, не проверен
REVIEWED = "reviewed"          # проверено человеком
APPROVED = "approved"          # утверждено
STALE = "stale"                # источник изменился, перевод не менялся
CONFLICT = "conflict"          # изменились и источник, и перевод (извне)
ORPHAN = "orphan"              # источник удалён, перевод остался
EXTRA = "extra"                # ключ есть только в целевом языке мода
NATIVE = "native"              # родной перевод мода, истории нет (untracked)
EXTERNAL = "external"          # переведено сторонним модом-русификатором
EDITED_OUTSIDE = "edited_outside"  # записанный файл правили вне приложения
ABSENT = "absent"              # ключа нет нигде

# Статусы, при которых перевод считается пригодным для записи
WRITABLE = {MACHINE, REVIEWED, APPROVED, STALE, EDITED_OUTSIDE}


@dataclass
class RowState:
    key: str
    status: str
    source_text: str | None = None
    baseline_source: str | None = None  # источник на момент перевода
    target_text: str | None = None      # наш перевод (из базы)
    native_target: str | None = None    # родной перевод в самом моде
    same_as_source: bool = False        # «перевод» совпадает с оригиналом


def compute_row_state(
    key: str,
    source_value: str | None,
    unit: dict | None,
    native_target_value: str | None = None,
    written_target_value: str | None = None,
    external: bool = False,
) -> RowState:
    """Статус одной строки.

    source_value          — текущее значение в исходном языке мода
    unit                  — запись translation_units (dict-подобная) или None
    native_target_value   — значение целевого языка в самом моде (если есть)
    written_target_value  — значение в записанном нами файле (если читали диск)
    """
    unit_target = (unit or {}).get("target_text") or None
    baseline = (unit or {}).get("source_text") or None
    baseline_hash = (unit or {}).get("source_hash") or ""
    written_hash_db = (unit or {}).get("target_hash_written") or ""
    unit_status = (unit or {}).get("status") or ""

    def _state(status: str) -> RowState:
        return RowState(
            key=key,
            status=status,
            source_text=source_value,
            baseline_source=baseline,
            target_text=unit_target,
            native_target=native_target_value,
            same_as_source=(
                source_value is not None
                and unit_target is not None
                and source_value.strip() == unit_target.strip()
            ),
        )

    # --- источника больше нет ---
    if source_value is None:
        if unit_target:
            return _state(ORPHAN)
        if native_target_value is not None:
            return _state(EXTRA)
        return _state(ABSENT)

    # --- источник есть, нашего перевода нет ---
    if not unit_target:
        if native_target_value is not None:
            return _state(NATIVE)
        if external:
            # строку уже перевёл отдельный мод-русификатор
            return _state(EXTERNAL)
        return _state(MISSING)

    # --- наш перевод есть: сверяем источник с BASE ---
    externally_edited = bool(
        written_target_value is not None
        and written_hash_db
        and semantic_hash(written_target_value) != written_hash_db
    )
    source_changed = baseline_hash != semantic_hash(source_value)

    if source_changed and externally_edited:
        return _state(CONFLICT)
    if source_changed:
        return _state(STALE)
    if externally_edited:
        return _state(EDITED_OUTSIDE)

    # актуален; степень проверки — из workflow-статуса юнита
    if unit_status in (MACHINE, REVIEWED, APPROVED):
        return _state(unit_status)
    return _state(MACHINE)


def project_rows(
    source_keys: dict[str, str],
    units: dict[str, dict],
    native_target_keys: dict[str, str] | None = None,
    written_target_keys: dict[str, str] | None = None,
    external_keys: set[str] | None = None,
) -> list[RowState]:
    """Статусы всех строк проекта: объединение ключей источника,
    базы переводов и целевого языка мода."""
    native = native_target_keys or {}
    written = written_target_keys or {}
    external = external_keys or set()
    all_keys = sorted(set(source_keys) | set(units) | set(native))
    out = []
    for key in all_keys:
        out.append(
            compute_row_state(
                key,
                source_keys.get(key),
                dict(units[key]) if key in units else None,
                native.get(key),
                written.get(key),
                external=key in external,
            )
        )
    return [r for r in out if r.status != ABSENT]
