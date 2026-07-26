"""Lossless-парсер файлов локализации CK3.

Формат CK3 похож на YAML, но им не является; поэтому здесь построчный
разбор с гарантией: если ни одна строка не изменена, сериализация
возвращает исходные байты один в один (BOM, переводы строк, отступы,
комментарии, битые строки — всё сохраняется).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BOM = b"\xef\xbb\xbf"

# Виды строк
HEADER = "header"
ENTRY = "entry"
COMMENT = "comment"
BLANK = "blank"
UNKNOWN = "unknown"

_HEADER_RE = re.compile(r"^\s*l_([A-Za-z0-9_\-]+):\s*(?:#.*)?$")
# ключ: всё до двоеточия без пробелов/кавычек/решётки
_ENTRY_START_RE = re.compile(r'^(\s*)([^\s:#"]+):(\d*)(\s*)"')


@dataclass
class Line:
    """Одна строка файла. raw — исходные байты, включая терминатор
    (и BOM, если это первая строка файла)."""

    raw: bytes
    kind: str
    text: str  # декодированный текст без BOM и без терминатора
    eol: bytes  # b"\r\n" | b"\n" | b"" (последняя строка без переноса)
    has_bom: bool = False
    decode_ok: bool = True  # False → менять строку нельзя, только raw
    lineno: int = 0

    # только для ENTRY:
    key: str | None = None
    number: str | None = None  # "" если числа после двоеточия нет
    q1: int = -1  # индекс открывающей кавычки в text
    q2: int = -1  # индекс закрывающей кавычки в text
    lang: str | None = None  # только для HEADER

    _new_value: str | None = field(default=None, repr=False)

    # --- значение ---

    @property
    def raw_value(self) -> str | None:
        """Значение как в файле, между кавычками (с \\" и литеральным \\n)."""
        if self.kind != ENTRY:
            return None
        if self._new_value is not None:
            return encode_value(self._new_value)
        return self.text[self.q1 + 1 : self.q2]

    @property
    def value(self) -> str | None:
        """Декодированное значение (\\" → \")."""
        raw = self.raw_value
        return None if raw is None else decode_value(raw)

    def set_value(self, new_value: str) -> None:
        """Заменить значение записи. Меняется только участок между кавычками."""
        if self.kind != ENTRY:
            raise ValueError("set_value допустим только для строк-записей")
        if not self.decode_ok:
            raise ValueError(
                f"строка {self.lineno}: исходные байты не являются корректным "
                f"UTF-8, редактирование запрещено"
            )
        self._new_value = new_value

    @property
    def dirty(self) -> bool:
        return self._new_value is not None

    # --- сериализация ---

    def render(self) -> bytes:
        if self._new_value is None:
            return self.raw
        new_text = (
            self.text[: self.q1 + 1]
            + encode_value(self._new_value)
            + self.text[self.q2 :]
        )
        prefix = BOM if self.has_bom else b""
        return prefix + new_text.encode("utf-8") + self.eol


def decode_value(raw: str) -> str:
    """Из файла в текст: \\" → \". Литеральный \\n не трогаем."""
    return raw.replace('\\"', '"')


def encode_value(value: str) -> str:
    """Из текста в файл: \" → \\". Уже экранированные не задваиваем."""
    # сначала снимем возможное существующее экранирование, затем поставим своё
    return value.replace('\\"', '"').replace('"', '\\"')


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning"
    code: str
    message: str
    lineno: int = 0


@dataclass
class LocFile:
    """Разобранный файл локализации."""

    path: Path | None
    lines: list[Line]
    had_bom: bool

    # --- разбор ---

    @classmethod
    def parse_bytes(cls, data: bytes, path: Path | None = None) -> "LocFile":
        had_bom = data.startswith(BOM)
        raw_lines = data.splitlines(keepends=True)
        lines: list[Line] = []
        for i, raw in enumerate(raw_lines):
            first = i == 0
            lines.append(_parse_line(raw, first and had_bom, i + 1))
        return cls(path=path, lines=lines, had_bom=had_bom)

    @classmethod
    def load(cls, path: Path) -> "LocFile":
        return cls.parse_bytes(Path(path).read_bytes(), path=Path(path))

    # --- сериализация ---

    def to_bytes(self) -> bytes:
        return b"".join(line.render() for line in self.lines)

    # --- доступ ---

    def entries(self) -> list[Line]:
        return [l for l in self.lines if l.kind == ENTRY]

    @property
    def header_lang(self) -> str | None:
        """Язык из первого заголовка l_<lang>: (главный признак языка файла)."""
        for l in self.lines:
            if l.kind == HEADER:
                return l.lang
        return None

    @property
    def dirty(self) -> bool:
        return any(l.dirty for l in self.lines)

    def get(self, key: str) -> Line | None:
        """Первое вхождение ключа."""
        for l in self.lines:
            if l.kind == ENTRY and l.key == key:
                return l
        return None

    # --- диагностика ---

    def diagnostics(self) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        headers = [l for l in self.lines if l.kind == HEADER]
        if not headers:
            out.append(
                Diagnostic("error", "no_header", "нет заголовка языка (l_...:)")
            )
        if len(headers) > 1:
            out.append(
                Diagnostic(
                    "warning",
                    "multiple_headers",
                    f"несколько заголовков языка ({len(headers)})",
                    headers[1].lineno,
                )
            )
        seen: dict[str, int] = {}
        for l in self.lines:
            if l.kind == UNKNOWN and l.text.strip():
                out.append(
                    Diagnostic(
                        "warning",
                        "unparsed_line",
                        f"нераспознанная строка: {l.text.strip()[:80]}",
                        l.lineno,
                    )
                )
            if l.kind == ENTRY:
                if l.key in seen:
                    out.append(
                        Diagnostic(
                            "warning",
                            "duplicate_key",
                            f"дубликат ключа {l.key} "
                            f"(первое вхождение — строка {seen[l.key]})",
                            l.lineno,
                        )
                    )
                else:
                    seen[l.key] = l.lineno
            if not l.decode_ok:
                out.append(
                    Diagnostic(
                        "error",
                        "bad_encoding",
                        "строка содержит байты, не являющиеся корректным UTF-8",
                        l.lineno,
                    )
                )
        return out


def _split_eol(raw: bytes) -> tuple[bytes, bytes]:
    if raw.endswith(b"\r\n"):
        return raw[:-2], b"\r\n"
    if raw.endswith(b"\n"):
        return raw[:-1], b"\n"
    if raw.endswith(b"\r"):
        return raw[:-1], b"\r"
    return raw, b""


def _parse_line(raw: bytes, has_bom: bool, lineno: int) -> Line:
    body, eol = _split_eol(raw)
    if has_bom:
        body = body[len(BOM) :]

    try:
        text = body.decode("utf-8")
        decode_ok = True
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="replace")
        decode_ok = False

    base = dict(raw=raw, text=text, eol=eol, has_bom=has_bom, lineno=lineno,
                decode_ok=decode_ok)

    if not decode_ok:
        return Line(kind=UNKNOWN, **base)

    stripped = text.strip()
    if not stripped:
        return Line(kind=BLANK, **base)
    if stripped.startswith("#"):
        return Line(kind=COMMENT, **base)

    m = _HEADER_RE.match(text)
    if m:
        return Line(kind=HEADER, lang=m.group(1), **base)

    m = _ENTRY_START_RE.match(text)
    if m:
        q1 = m.end() - 1  # позиция открывающей кавычки
        q2 = text.rfind('"')
        if q2 > q1:
            return Line(
                kind=ENTRY,
                key=m.group(2),
                number=m.group(3),
                q1=q1,
                q2=q2,
                **base,
            )
    return Line(kind=UNKNOWN, **base)


def build_new_file(
    lang: str, items: list[tuple[str, str]], eol: str = "\r\n"
) -> bytes:
    """Собрать новый файл локализации с нуля: UTF-8 BOM, заголовок, записи.

    items — пары (ключ, декодированное значение).
    """
    parts = [f"l_{lang}:"]
    for key, value in items:
        parts.append(f' {key}: "{encode_value(value)}"')
    return BOM + eol.join(parts).encode("utf-8") + eol.encode("utf-8")
