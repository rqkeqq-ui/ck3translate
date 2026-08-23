"""Сканер локализаций: моды мастерской, языки, ключи, полнота, диагностика.

Всё — только чтение. Единица учёта — ключ; файл — происхождение ключа.
"""

from __future__ import annotations

import hashlib
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from .descriptor import Descriptor
from .locparser import ENTRY, Diagnostic, LocFile

# Резервный список языков CK3 (основной источник — установленная игра)
DEFAULT_LANGUAGES = [
    "english",
    "french",
    "german",
    "spanish",
    "russian",
    "simp_chinese",
    "korean",
    "polish",
    "japanese",
]


def semantic_hash(value: str) -> str:
    """Отпечаток значения строки. Не зависит от места строки в файле,
    комментариев и перевода строк файла."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass
class KeyOccurrence:
    key: str
    value: str
    lineno: int
    rel_path: str  # путь файла относительно папки мода
    language: str
    replace_scope: bool
    number: str = ""

    @property
    def value_hash(self) -> str:
        return semantic_hash(self.value)


@dataclass
class FileScan:
    path: Path
    rel_path: str
    header_lang: str | None
    name_lang: str | None
    path_lang: str | None
    replace_scope: bool
    entry_count: int
    occurrences: list[KeyOccurrence]
    diagnostics: list[Diagnostic]
    raw_size: int
    raw_hash: str

    @property
    def effective_lang(self) -> str | None:
        """Главный признак — заголовок; имя и путь — проверочные."""
        return self.header_lang or self.name_lang or self.path_lang


@dataclass
class LanguageSummary:
    language: str
    file_count: int = 0
    keys: dict[str, KeyOccurrence] = field(default_factory=dict)
    duplicates: list[KeyOccurrence] = field(default_factory=list)

    @property
    def key_count(self) -> int:
        return len(self.keys)


@dataclass
class ModScan:
    mod_id: str
    mod_dir: Path
    descriptor: Descriptor
    files: list[FileScan] = field(default_factory=list)
    languages: dict[str, LanguageSummary] = field(default_factory=dict)
    diagnostics: list[tuple[str, Diagnostic]] = field(default_factory=list)
    source_language_hint: str = ""

    @property
    def name(self) -> str:
        return self.descriptor.name or self.mod_id

    @property
    def has_localization(self) -> bool:
        return bool(self.files)

    def coverage(self, target: str, source: str = "english") -> tuple[int, int]:
        """(переведено, всего в источнике). Считает по ключам."""
        src = self.languages.get(source)
        tgt = self.languages.get(target)
        if not src or not src.keys:
            return (0, 0)
        if not tgt:
            return (0, len(src.keys))
        translated = len(set(src.keys) & set(tgt.keys))
        return (translated, len(src.keys))

    def missing_keys(self, target: str, source: str = "english") -> list[str]:
        src = self.languages.get(source)
        tgt = self.languages.get(target)
        if not src:
            return []
        tgt_keys = set(tgt.keys) if tgt else set()
        return [k for k in src.keys if k not in tgt_keys]

    def extra_keys(self, target: str, source: str = "english") -> list[str]:
        """Ключи только целевого языка — решение за человеком."""
        src = self.languages.get(source)
        tgt = self.languages.get(target)
        if not tgt:
            return []
        src_keys = set(src.keys) if src else set()
        return [k for k in tgt.keys if k not in src_keys]

    def best_source_language(self, preferred: str = "english") -> str | None:
        """Самый полный язык мода (авто-подсказка источника)."""
        if not self.languages:
            return None
        best = max(
            self.languages.values(),
            key=lambda s: (s.key_count, s.language == preferred),
        )
        pref = self.languages.get(preferred)
        if pref and pref.key_count >= best.key_count:
            return preferred
        return best.language


def detect_langs_from_path(
    rel_parts: tuple[str, ...], known: list[str]
) -> tuple[str | None, bool]:
    """(язык из пути, replace_scope) по компонентам пути внутри localization."""
    known_set = set(known)
    lang = None
    replace = False
    for part in rel_parts:
        low = part.lower()
        if low == "replace":
            replace = True
        elif low in known_set and lang is None:
            lang = low
    return lang, replace


def detect_lang_from_name(filename: str, known: list[str]) -> str | None:
    low = filename.lower()
    for lang in known:
        if low.endswith(f"_l_{lang}.yml"):
            return lang
    return None


def scan_localization_tree(
    mod_dir: Path,
    known_languages: list[str] | None = None,
    exclude_globs: tuple[str, ...] = (),
) -> list[FileScan]:
    """Рекурсивно разобрать все .yml под localization/ папки мода."""
    known = known_languages or DEFAULT_LANGUAGES
    loc_root = Path(mod_dir) / "localization"
    result: list[FileScan] = []
    if not loc_root.is_dir():
        return result
    for path in sorted(loc_root.rglob("*.yml")):
        if not path.is_file():
            continue
        rel_path = str(path.relative_to(mod_dir)).replace("\\", "/")
        if any(
            fnmatch.fnmatchcase(rel_path.casefold(), pattern.casefold())
            for pattern in exclude_globs
        ):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        loc = LocFile.parse_bytes(data, path=path)
        rel_to_loc = path.relative_to(loc_root)
        path_lang, replace_scope = detect_langs_from_path(
            rel_to_loc.parts[:-1], known
        )
        name_lang = detect_lang_from_name(path.name, known)
        header_lang = loc.header_lang

        diags = loc.diagnostics()
        langs_seen = {
            l for l in (header_lang, name_lang, path_lang) if l is not None
        }
        if len(langs_seen) > 1:
            diags.append(
                Diagnostic(
                    "warning",
                    "lang_mismatch",
                    f"расхождение языка: заголовок={header_lang}, "
                    f"имя={name_lang}, путь={path_lang}",
                )
            )

        effective = header_lang or name_lang or path_lang
        occurrences = []
        if effective:
            for e in loc.entries():
                occurrences.append(
                    KeyOccurrence(
                        key=e.key,
                        value=e.value,
                        lineno=e.lineno,
                        rel_path=rel_path,
                        language=effective,
                        replace_scope=replace_scope,
                        number=e.number or "",
                    )
                )
        result.append(
            FileScan(
                path=path,
                rel_path=rel_path,
                header_lang=header_lang,
                name_lang=name_lang,
                path_lang=path_lang,
                replace_scope=replace_scope,
                entry_count=len(occurrences),
                occurrences=occurrences,
                diagnostics=diags,
                raw_size=len(data),
                raw_hash=hashlib.sha256(data).hexdigest()[:16],
            )
        )
    return result


def scan_mod(
    mod_dir: Path,
    known_languages: list[str] | None = None,
    rule=None,
) -> ModScan:
    mod_dir = Path(mod_dir)
    scan = ModScan(
        mod_id=mod_dir.name,
        mod_dir=mod_dir,
        descriptor=Descriptor.load(mod_dir),
        source_language_hint=(getattr(rule, "source_language", "") if rule else ""),
    )
    excludes = tuple(getattr(rule, "exclude_globs", ())) if rule else ()
    ignored_prefixes = tuple(
        getattr(rule, "protected_key_prefixes", ())
    ) if rule else ()
    scan.files = scan_localization_tree(mod_dir, known_languages, excludes)
    for fs in scan.files:
        for d in fs.diagnostics:
            scan.diagnostics.append((fs.rel_path, d))
        lang = fs.effective_lang
        if lang is None:
            continue
        summary = scan.languages.setdefault(lang, LanguageSummary(language=lang))
        summary.file_count += 1
        for occ in fs.occurrences:
            if ignored_prefixes and occ.key.startswith(ignored_prefixes):
                continue
            if occ.key in summary.keys:
                # replace-файлы законно переопределяют ключи; настоящие
                # дубликаты внутри одного скоупа уже отмечены парсером
                if occ.replace_scope:
                    summary.keys[occ.key] = occ
                else:
                    summary.duplicates.append(occ)
            else:
                summary.keys[occ.key] = occ
    return scan


def localization_fingerprint(scan: ModScan) -> str:
    """Семантический отпечаток всей локализации мода: не зависит от
    порядка файлов/строк, комментариев и переводов строк."""
    h = hashlib.sha256()
    for lang in sorted(scan.languages):
        summary = scan.languages[lang]
        for key in sorted(summary.keys):
            occ = summary.keys[key]
            h.update(f"{lang}\x00{key}\x00{occ.value}\x01".encode("utf-8"))
    return h.hexdigest()[:16]
