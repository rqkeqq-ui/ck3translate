"""Безопасное чтение подписной CK3Loc Community Database из Workshop.

База содержит только JSON-данные. Пути к файлам намеренно зафиксированы в
коде: содержимое Workshop не может заставить приложение прочитать или
запустить что-либо за пределами каталога подписки.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ck3loc import __version__

from .steam import read_workshop_acf, workshop_content_dirs

PRODUCT = "ck3loc-community-database"
SUPPORTED_SCHEMA = 1
MARKER_FILE = "ck3loc-database.json"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_GLOSSARY_TERMS = 20_000
MAX_REGISTRY_ITEMS = 20_000
VALID_MODES = {"required", "preferred", "forbidden"}


class CommunityDatabaseError(ValueError):
    """Файл базы существует, но не прошёл проверку."""


@dataclass(frozen=True)
class GlossaryTerm:
    source_lang: str
    target_lang: str
    source_term: str
    target_term: str
    mode: str = "preferred"
    note: str = ""


@dataclass(frozen=True)
class RegisteredTranslation:
    source_mod_id: str
    provider_mod_id: str
    source_lang: str
    target_lang: str


@dataclass(frozen=True)
class ModRule:
    mod_id: str
    source_language: str = ""
    exclude_globs: tuple[str, ...] = ()
    protected_key_prefixes: tuple[str, ...] = ()


@dataclass
class CommunityDatabase:
    root: Path
    workshop_id: str
    database_version: str
    minimum_app_version: str
    compatible: bool
    glossaries: list[GlossaryTerm] = field(default_factory=list)
    translations: list[RegisteredTranslation] = field(default_factory=list)
    mod_rules: dict[str, ModRule] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    state: str  # ready | missing | downloading | invalid | incompatible | disabled
    database: CommunityDatabase | None = None
    workshop_id: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GlossaryImportResult:
    added: int = 0
    updated: int = 0
    skipped_user: int = 0


def _safe_text(value, field_name: str, max_len: int = 500) -> str:
    if not isinstance(value, str):
        raise CommunityDatabaseError(f"{field_name}: ожидалась строка")
    value = value.strip()
    if len(value) > max_len:
        raise CommunityDatabaseError(f"{field_name}: значение слишком длинное")
    return value


def _mod_id(value, field_name: str) -> str:
    value = _safe_text(value, field_name, 32)
    if not value.isdigit():
        raise CommunityDatabaseError(f"{field_name}: нужен числовой Workshop ID")
    return value


def _read_json(path: Path, required: bool = True):
    if not path.is_file():
        if required:
            raise CommunityDatabaseError(f"не найден файл {path.name}")
        return None
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CommunityDatabaseError(f"не удалось прочитать {path.name}: {exc}") from exc
    if size > MAX_JSON_BYTES:
        raise CommunityDatabaseError(
            f"{path.name}: размер превышает {MAX_JSON_BYTES // 1024} КБ"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommunityDatabaseError(f"повреждён {path.name}: {exc}") from exc


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts or [0])


def configured_workshop_id() -> str:
    """ID опубликованной базы: env для разработки, затем пакетный config."""
    override = os.environ.get("CK3LOC_COMMUNITY_DB_ID", "").strip()
    if override:
        return override if override.isdigit() else ""
    config = Path(__file__).resolve().parent.parent / "community_db_config.json"
    try:
        value = json.loads(config.read_text(encoding="utf-8")).get("workshop_id", "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    value = str(value).strip()
    return value if value.isdigit() else ""


def configured_repository_url() -> str:
    config = Path(__file__).resolve().parent.parent / "community_db_config.json"
    try:
        value = json.loads(config.read_text(encoding="utf-8")).get(
            "repository_url", ""
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    return value.strip() if isinstance(value, str) else ""


def load_community_database(root: Path, expected_id: str = "") -> CommunityDatabase:
    root = Path(root)
    marker = _read_json(root / MARKER_FILE)
    if not isinstance(marker, dict):
        raise CommunityDatabaseError(f"{MARKER_FILE}: ожидался JSON-объект")
    if marker.get("product") != PRODUCT:
        raise CommunityDatabaseError("неверный идентификатор продукта")
    if marker.get("schema_version") != SUPPORTED_SCHEMA:
        raise CommunityDatabaseError(
            f"неподдерживаемая схема {marker.get('schema_version')!r}; "
            f"ожидалась {SUPPORTED_SCHEMA}"
        )

    folder_id = root.name if root.name.isdigit() else ""
    declared_id = str(marker.get("workshop_id") or "").strip()
    if declared_id and not declared_id.isdigit():
        raise CommunityDatabaseError("workshop_id должен быть числовым")
    actual_id = expected_id or folder_id or declared_id
    if expected_id and folder_id and folder_id != expected_id:
        raise CommunityDatabaseError("папка не совпадает с ожидаемым Workshop ID")
    if declared_id and actual_id and declared_id != actual_id:
        raise CommunityDatabaseError("workshop_id в marker не совпадает с папкой")

    database_version = _safe_text(
        marker.get("database_version", ""), "database_version", 64
    )
    minimum = _safe_text(
        marker.get("minimum_app_version", "0"), "minimum_app_version", 32
    )
    compatible = _version_tuple(__version__) >= _version_tuple(minimum)
    warnings: list[str] = []
    if not actual_id:
        warnings.append("Workshop ID ещё не указан; допустимо только до публикации")

    glossaries = _load_glossaries(root / "glossary" / "glossaries.json")
    translations = _load_translations(
        root / "registry" / "translation_mods.json"
    )
    rules = _load_mod_rules(root / "registry" / "mod_rules.json")
    return CommunityDatabase(
        root=root,
        workshop_id=actual_id,
        database_version=database_version,
        minimum_app_version=minimum,
        compatible=compatible,
        glossaries=glossaries,
        translations=translations,
        mod_rules=rules,
        warnings=warnings,
    )


def _load_glossaries(path: Path) -> list[GlossaryTerm]:
    data = _read_json(path, required=False)
    if data is None:
        return []
    if not isinstance(data, list) or len(data) > MAX_GLOSSARY_TERMS:
        raise CommunityDatabaseError("glossaries.json: неверный список терминов")
    out: list[GlossaryTerm] = []
    seen: set[tuple[str, str, str]] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise CommunityDatabaseError(f"glossaries.json[{i}]: ожидался объект")
        source_lang = _safe_text(item.get("source_lang", ""), "source_lang", 32)
        target_lang = _safe_text(item.get("target_lang", ""), "target_lang", 32)
        source = _safe_text(item.get("source_term", ""), "source_term", 300)
        target = _safe_text(item.get("target_term", ""), "target_term", 500)
        mode = _safe_text(item.get("mode", "preferred"), "mode", 20)
        note = _safe_text(item.get("note", ""), "note", 500)
        if not source_lang or not target_lang or not source:
            raise CommunityDatabaseError(f"glossaries.json[{i}]: пустое обязательное поле")
        if mode not in VALID_MODES:
            raise CommunityDatabaseError(f"glossaries.json[{i}]: неизвестный mode")
        key = (source_lang, target_lang, source.casefold())
        if key in seen:
            raise CommunityDatabaseError(f"glossaries.json[{i}]: дубликат термина")
        seen.add(key)
        out.append(GlossaryTerm(source_lang, target_lang, source, target, mode, note))
    return out


def _load_translations(path: Path) -> list[RegisteredTranslation]:
    data = _read_json(path, required=False)
    if data is None:
        return []
    if not isinstance(data, list) or len(data) > MAX_REGISTRY_ITEMS:
        raise CommunityDatabaseError("translation_mods.json: неверный список")
    out: list[RegisteredTranslation] = []
    seen: set[tuple[str, str, str]] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise CommunityDatabaseError(f"translation_mods.json[{i}]: ожидался объект")
        source = _mod_id(item.get("source_mod_id", ""), "source_mod_id")
        provider = _mod_id(item.get("provider_mod_id", ""), "provider_mod_id")
        source_lang = _safe_text(item.get("source_lang", "english"), "source_lang", 32)
        target_lang = _safe_text(item.get("target_lang", ""), "target_lang", 32)
        key = (source, provider, target_lang)
        if source == provider or not target_lang or key in seen:
            raise CommunityDatabaseError(f"translation_mods.json[{i}]: неверная связь")
        seen.add(key)
        out.append(RegisteredTranslation(source, provider, source_lang, target_lang))
    return out


def _load_mod_rules(path: Path) -> dict[str, ModRule]:
    data = _read_json(path, required=False)
    if data is None:
        return {}
    if not isinstance(data, dict) or len(data) > MAX_REGISTRY_ITEMS:
        raise CommunityDatabaseError("mod_rules.json: ожидался объект")
    out: dict[str, ModRule] = {}
    for raw_id, item in data.items():
        mod_id = _mod_id(raw_id, "mod_rules key")
        if not isinstance(item, dict):
            raise CommunityDatabaseError(f"mod_rules[{mod_id}]: ожидался объект")
        source_language = _safe_text(
            item.get("source_language", ""), "source_language", 32
        )
        excludes = item.get("exclude_globs", [])
        prefixes = item.get("protected_key_prefixes", [])
        if not isinstance(excludes, list) or not isinstance(prefixes, list):
            raise CommunityDatabaseError(f"mod_rules[{mod_id}]: ожидались списки")
        if len(excludes) > 100 or len(prefixes) > 100:
            raise CommunityDatabaseError(f"mod_rules[{mod_id}]: слишком много правил")
        out[mod_id] = ModRule(
            mod_id,
            source_language,
            tuple(_safe_text(v, "exclude_glob", 200) for v in excludes),
            tuple(_safe_text(v, "protected_key_prefix", 100) for v in prefixes),
        )
    return out


def discover_community_database(
    steam_root: Path | None = None,
    *,
    content_dirs: list[Path] | None = None,
    preferred_id: str | None = None,
    enabled: bool = True,
) -> DiscoveryResult:
    if not enabled:
        return DiscoveryResult("disabled")
    preferred = configured_workshop_id() if preferred_id is None else preferred_id
    preferred = preferred if preferred.isdigit() else ""
    contents = content_dirs if content_dirs is not None else workshop_content_dirs(steam_root)
    candidates: list[Path] = []
    if preferred:
        candidates.extend(d / preferred for d in contents if (d / preferred).is_dir())
    # После публикации принимаем только канонический ID. Поиск marker-файла
    # среди всех подписок нужен лишь staging-сборкам, где ID ещё неизвестен.
    if not preferred:
        for content in contents:
            try:
                children = sorted(content.iterdir())
            except OSError:
                continue
            for child in children:
                if (
                    child.is_dir()
                    and child.name.isdigit()
                    and (child / MARKER_FILE).is_file()
                    and child not in candidates
                ):
                    candidates.append(child)

    errors: list[str] = []
    for candidate in candidates:
        try:
            database = load_community_database(
                candidate, expected_id=preferred if candidate.name == preferred else ""
            )
        except CommunityDatabaseError as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        return DiscoveryResult(
            "ready" if database.compatible else "incompatible",
            database=database,
            workshop_id=database.workshop_id,
            errors=errors,
        )

    if errors:
        return DiscoveryResult("invalid", workshop_id=preferred, errors=errors)
    if preferred and content_dirs is None:
        installed = read_workshop_acf(steam_root)
        if preferred in installed:
            return DiscoveryResult("downloading", workshop_id=preferred)
    return DiscoveryResult("missing", workshop_id=preferred)


def import_community_glossary(conn, database: CommunityDatabase) -> GlossaryImportResult:
    """Синхронизировать термины, не меняя строки, отредактированные человеком."""
    if not database.compatible:
        return GlossaryImportResult()
    origin = f"community:{database.workshop_id or 'staging'}"
    conn.execute("SAVEPOINT community_glossary")
    try:
        added = updated = skipped = 0
        incoming = {
            (term.source_lang, term.target_lang, term.source_term)
            for term in database.glossaries
        }
        old_rows = conn.execute(
            """SELECT id, source_lang, target_lang, source_term
               FROM glossary_terms WHERE origin=?""",
            (origin,),
        ).fetchall()
        for row in old_rows:
            key = (row["source_lang"], row["target_lang"], row["source_term"])
            if key not in incoming:
                conn.execute("DELETE FROM glossary_terms WHERE id=?", (row["id"],))
        for term in database.glossaries:
            rows = conn.execute(
                """SELECT id, origin, target_term, mode, note
                   FROM glossary_terms
                   WHERE level='global' AND source_lang=? AND target_lang=?
                     AND source_term=? ORDER BY id DESC""",
                (term.source_lang, term.target_lang, term.source_term),
            ).fetchall()
            if any(row["origin"] == "user" for row in rows):
                skipped += 1
                continue
            if any(row["origin"] == "builtin" and row["target_term"] == term.target_term
                   and row["mode"] == term.mode for row in rows):
                conn.execute(
                    "DELETE FROM glossary_terms WHERE level='global' AND source_lang=? AND target_lang=? AND source_term=? AND origin=?",
                    (term.source_lang, term.target_lang, term.source_term, origin),
                )
                skipped += 1
                continue
            row = next((row for row in rows if row["origin"] == origin), None)
            if row is None:
                conn.execute(
                    """INSERT INTO glossary_terms
                           (level, source_lang, target_lang, source_term,
                            target_term, mode, note, origin)
                       VALUES ('global', ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        term.source_lang, term.target_lang, term.source_term,
                        term.target_term, term.mode, term.note, origin,
                    ),
                )
                added += 1
            elif (
                row["target_term"] != term.target_term
                or row["mode"] != term.mode
                or row["note"] != term.note
                or row["origin"] != origin
            ):
                conn.execute(
                    """UPDATE glossary_terms
                       SET target_term=?, mode=?, note=?, origin=? WHERE id=?""",
                    (term.target_term, term.mode, term.note, origin, row["id"]),
                )
                updated += 1
        conn.execute("RELEASE SAVEPOINT community_glossary")
        conn.commit()
        return GlossaryImportResult(added, updated, skipped)
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT community_glossary")
        conn.execute("RELEASE SAVEPOINT community_glossary")
        raise


def clear_community_glossary(conn) -> int:
    """Убрать подписные строки; пользовательские правки и builtin остаются."""
    cur = conn.execute(
        "DELETE FROM glossary_terms WHERE origin LIKE 'community:%'"
    )
    conn.commit()
    return max(0, cur.rowcount)


def workshop_page_url(workshop_id: str = "") -> str:
    item_id = workshop_id or configured_workshop_id()
    return (
        f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"
        if item_id.isdigit() else ""
    )
