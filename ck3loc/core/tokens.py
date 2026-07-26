"""Лексер игровых кодов CK3: защита перед переводом, проверка после.

Кодовые конструкции:
  $KEY$            — подстановка строки локализации
  [Scope.Fn(...)]  — вызов функции (скобки могут вкладываться)
  @icon!           — иконка
  #tag ... #!      — форматирование (парные теги)
  \\n              — литеральный перенос строки
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# защитный маркер: символы, которые переводчики не трогают
MARK_OPEN = "⟦"   # ⟦
MARK_CLOSE = "⟧"  # ⟧

_MARK_RE = re.compile(rf"{MARK_OPEN}T(\d+){MARK_CLOSE}")
_ICON_RE = re.compile(r"@[A-Za-z0-9_.\-]+!")
_FMT_OPEN_RE = re.compile(r"#[A-Za-z][A-Za-z0-9_;:]*")


@dataclass
class Token:
    kind: str  # text | dollar | bracket | icon | fmt_open | fmt_close | newline
    text: str


def tokenize(value: str) -> list[Token]:
    tokens: list[Token] = []
    buf: list[str] = []
    i = 0
    n = len(value)

    def flush():
        if buf:
            tokens.append(Token("text", "".join(buf)))
            buf.clear()

    while i < n:
        ch = value[i]
        if ch == "$":
            j = value.find("$", i + 1)
            if j != -1:
                flush()
                tokens.append(Token("dollar", value[i : j + 1]))
                i = j + 1
                continue
        elif ch == "[":
            depth = 0
            j = i
            while j < n:
                if value[j] == "[":
                    depth += 1
                elif value[j] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j < n and depth == 0:
                flush()
                tokens.append(Token("bracket", value[i : j + 1]))
                i = j + 1
                continue
        elif ch == "@":
            m = _ICON_RE.match(value, i)
            if m:
                flush()
                tokens.append(Token("icon", m.group(0)))
                i = m.end()
                continue
        elif ch == "#":
            if value.startswith("#!", i):
                flush()
                tokens.append(Token("fmt_close", "#!"))
                i += 2
                continue
            m = _FMT_OPEN_RE.match(value, i)
            if m:
                flush()
                tokens.append(Token("fmt_open", m.group(0)))
                i = m.end()
                continue
        elif ch == "\\" and i + 1 < n and value[i + 1] == "n":
            flush()
            tokens.append(Token("newline", "\\n"))
            i += 2
            continue
        buf.append(ch)
        i += 1
    flush()
    return tokens


CODE_KINDS = {"dollar", "bracket", "icon", "fmt_open", "fmt_close", "newline"}


@dataclass
class Protected:
    text: str                       # текст с маркерами ⟦T1⟧…
    mapping: dict[str, str] = field(default_factory=dict)  # маркер → код


def protect(value: str) -> Protected:
    """Заменить все коды на маркеры ⟦Tn⟧."""
    tokens = tokenize(value)
    out: list[str] = []
    mapping: dict[str, str] = {}
    counter = 0
    for t in tokens:
        if t.kind in CODE_KINDS:
            counter += 1
            mark = f"{MARK_OPEN}T{counter}{MARK_CLOSE}"
            mapping[mark] = t.text
            out.append(mark)
        else:
            out.append(t.text)
    return Protected(text="".join(out), mapping=mapping)


def restore(protected_text: str, mapping: dict[str, str]) -> tuple[str, list[str]]:
    """Вернуть коды на место. Возвращает (строка, список проблем)."""
    problems: list[str] = []
    used: set[str] = set()

    def _sub(m: re.Match) -> str:
        mark = m.group(0)
        if mark not in mapping:
            problems.append(f"незнакомый маркер {mark}")
            return mark
        used.add(mark)
        return mapping[mark]

    result = _MARK_RE.sub(_sub, protected_text)
    missing = set(mapping) - used
    for mark in sorted(missing):
        problems.append(f"потерян маркер {mark} ({mapping[mark]})")
    if MARK_OPEN in result or MARK_CLOSE in result:
        problems.append("в тексте остались защитные скобки маркеров")
    return result, problems


def code_signature(value: str) -> dict[str, list[str]]:
    """Мультинабор кодов строки — для сравнения источника и перевода."""
    sig: dict[str, list[str]] = {
        "dollar": [], "bracket": [], "icon": [], "newline": [],
    }
    fmt_balance = 0
    fmt_opens: list[str] = []
    for t in tokenize(value):
        if t.kind in ("dollar", "bracket", "icon", "newline"):
            sig[t.kind].append(t.text)
        elif t.kind == "fmt_open":
            fmt_balance += 1
            fmt_opens.append(t.text)
        elif t.kind == "fmt_close":
            fmt_balance -= 1
    sig["fmt_opens"] = sorted(fmt_opens)
    sig["fmt_balance"] = [str(fmt_balance)]
    return sig


def validate_translation(source: str, target: str) -> list[str]:
    """Проверки после перевода (раздел 11 спецификации)."""
    errors: list[str] = []
    ssig = code_signature(source)
    tsig = code_signature(target)
    labels = {
        "dollar": "$…$",
        "bracket": "[…]",
        "icon": "@…!",
        "newline": "\\n",
    }
    for kind, label in labels.items():
        if sorted(ssig[kind]) != sorted(tsig[kind]):
            errors.append(
                f"набор {label} не совпадает: "
                f"{sorted(ssig[kind])} → {sorted(tsig[kind])}"
            )
    if tsig["fmt_balance"] != ["0"] and ssig["fmt_balance"] == ["0"]:
        errors.append("форматирующие теги #…#! не сбалансированы")
    if ssig["fmt_balance"] == ["0"] and ssig["fmt_opens"] != tsig["fmt_opens"]:
        errors.append(
            f"набор тегов форматирования изменён: "
            f"{ssig['fmt_opens']} → {tsig['fmt_opens']}"
        )
    # настоящий перенос строки допустим только там, где он есть в источнике
    # (некоторые моды пишут длинные описания в несколько строк)
    source_has_break = "\n" in source or "\r" in source
    if not source_has_break and ("\n" in target or "\r" in target):
        errors.append("настоящий перенос строки внутри значения недопустим")
    return errors
