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

# сколько строк максимум может занимать одно значение
MAX_MULTILINE_LINES = 200


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
        i = 0
        n = len(raw_lines)
        while i < n:
            has_bom = i == 0 and had_bom
            # значение может занимать несколько физических строк: кавычка
            # открыта здесь, а закрыта ниже — такие записи встречаются
            # в реальных модах, и игра их читает
            merged = _try_parse_multiline(raw_lines, i, has_bom)
            if merged is not None:
                line, consumed = merged
                lines.append(line)
                i += consumed
                continue
            lines.append(_parse_line(raw_lines[i], has_bom, i + 1))
            i += 1
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
                m = _ENTRY_START_RE.match(l.text)
                if m and _find_closing_quote(l.text, m.end()) == -1:
                    # частая ошибка авторов: забыта закрывающая кавычка,
                    # игра такую строку не прочитает
                    out.append(
                        Diagnostic(
                            "error",
                            "unterminated_quote",
                            f"не закрыта кавычка у ключа {m.group(2)} — "
                            f"игра не прочитает эту строку",
                            l.lineno,
                        )
                    )
                else:
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


def _decode_body(raw: bytes, has_bom: bool) -> tuple[str, bytes, bool]:
    """(текст без BOM и без терминатора, терминатор, корректный ли UTF-8)."""
    body, eol = _split_eol(raw)
    if has_bom:
        body = body[len(BOM) :]
    try:
        return body.decode("utf-8"), eol, True
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace"), eol, False


def _find_closing_quote(text: str, start: int) -> int:
    """Индекс неэкранированной закрывающей кавычки после start (или -1)."""
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            return i
        i += 1
    return -1


def _try_parse_multiline(
    raw_lines: list[bytes], index: int, has_bom: bool
) -> tuple[Line, int] | None:
    """Собрать запись, значение которой занимает несколько строк.

    Возвращает (строка-запись, сколько физических строк поглощено)
    или None, если здесь многострочная запись не начинается.
    """
    text, _eol, ok = _decode_body(raw_lines[index], has_bom)
    if not ok:
        return None
    m = _ENTRY_START_RE.match(text)
    if not m:
        return None
    q1 = m.end() - 1
    if _find_closing_quote(text, q1 + 1) != -1:
        return None  # обычная однострочная запись

    # ищем строку, где значение закрывается
    merged_text = text
    for j in range(index + 1, min(len(raw_lines), index + MAX_MULTILINE_LINES)):
        part, _e, part_ok = _decode_body(raw_lines[j], False)
        if not part_ok:
            return None
        # наткнулись на новую запись или заголовок языка — значит, кавычка
        # просто не закрыта, а не значение многострочное
        if _ENTRY_START_RE.match(part) or _HEADER_RE.match(part):
            return None
        prev_eol = _split_eol(raw_lines[j - 1])[1].decode("ascii", "replace")
        merged_text += prev_eol + part
        if _find_closing_quote(merged_text, q1 + 1) != -1:
            q2 = _find_closing_quote(merged_text, q1 + 1)
            raw = b"".join(raw_lines[index : j + 1])
            body_eol = _split_eol(raw_lines[j])[1]
            return (
                Line(
                    raw=raw,
                    kind=ENTRY,
                    text=merged_text,
                    eol=body_eol,
                    has_bom=has_bom,
                    decode_ok=True,
                    lineno=index + 1,
                    key=m.group(2),
                    number=m.group(3),
                    q1=q1,
                    q2=q2,
                ),
                j - index + 1,
            )
    return None  # кавычка так и не закрылась — оставляем как есть


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
