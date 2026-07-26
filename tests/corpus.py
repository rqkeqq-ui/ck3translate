"""Синтетический тестовый корпус файлов локализации CK3.

Образцы заданы байтами прямо в коде — это защищает их от порчи
редакторами и git (BOM, CRLF/LF, битые байты должны быть точными).
Функция materialize() записывает корпус в tests/fixtures/synthetic/.
"""

from __future__ import annotations

from pathlib import Path

BOM = b"\xef\xbb\xbf"

# name -> (relative path inside a fake mod, bytes)
SAMPLES: dict[str, tuple[str, bytes]] = {}


def _add(name: str, relpath: str, data: bytes) -> None:
    SAMPLES[name] = (relpath, data)


# 1. Базовый: BOM, CRLF, комментарии, key:0 и key:, пустые строки
_add(
    "basic_crlf_bom",
    "localization/english/basic_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' # comment line\r\n'
    + b'\r\n'
    + b' greeting: "Hello, world"\r\n'
    + b' old_style:0 "Zero style"\r\n'
    + b' numbered:15 "Fifteen"\r\n'
    + b' trailing: "Value"  # trailing comment\r\n',
)

# 2. LF без BOM
_add(
    "lf_nobom",
    "localization/english/lf_l_english.yml",
    b'l_english:\n key_a: "Alpha"\n key_b: "Beta"\n',
)

# 3. Экранированные кавычки, \n, игровые коды
_add(
    "codes_and_escapes",
    "localization/english/codes_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' quoted: "He said \\"stop\\" twice"\r\n'
    + b' newline: "First line\\nSecond line"\r\n'
    + b' icon: "@epe_icon_epe_rule!EPE: Enclosed Helmets"\r\n'
    + b' func: "[Character.GetFirstName] of [GetPlayer.GetPrimaryTitle.GetNameNoTier]"\r\n'
    + b' subst: "Cost: $VALUE|+0$ gold"\r\n'
    + b' fmt: "#T Title#! and #P positive#!"\r\n'
    + b' nested: "[Concept(\'realm\',\'Realm\')] rules"\r\n',
)

# 4. Дубликаты ключей
_add(
    "duplicate_keys",
    "localization/english/dup_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' same_key: "First"\r\n'
    + b' other: "Ok"\r\n'
    + b' same_key: "Second"\r\n',
)

# 5. Битые строки: без кавычек, одна кавычка, мусор, табы
_add(
    "broken_lines",
    "localization/english/broken_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' no_quotes: bare value\r\n'
    + b' one_quote: "unterminated\r\n'
    + b'\tjust garbage here\r\n'
    + b' good_key: "Good value"\r\n',
)

# 6. Смешанные переводы строк, последняя строка без EOL
_add(
    "mixed_eol",
    "localization/english/mixed_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' crlf_key: "CRLF line"\r\n'
    + b' lf_key: "LF line"\n'
    + b' last_key: "No trailing newline"',
)

# 7. Не-ASCII: кириллица и CJK в значениях
_add(
    "non_ascii",
    "localization/russian/rus_l_russian.yml",
    BOM
    + 'l_russian:\r\n холм: "Возвышенность"\r\n cjk: "汉字テスト"\r\n'.encode("utf-8"),
)

# 8. Файл в папке russian, но заголовок l_english (расхождение пути и заголовка)
_add(
    "path_mismatch",
    "localization/russian/mismatch_l_russian.yml",
    BOM + b'l_english:\r\n mism_key: "English text in russian folder"\r\n',
)

# 9. Битые байты (не UTF-8) в одной строке — файл не должен ронять парсер
_add(
    "invalid_utf8",
    "localization/english/badbytes_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' ok_key: "Fine"\r\n'
    + b' bad_key: "broken \xfe\xff bytes"\r\n'
    + b' after_key: "Still fine"\r\n',
)

# 10. Вложенная папка внутри языка
_add(
    "deep_nested",
    "localization/english/sub/deeper/deep_l_english.yml",
    BOM + b'l_english:\r\n deep_key: "Deep value"\r\n',
)

# 11. Форма replace #1: localization/replace/<lang>/
_add(
    "replace_form1",
    "localization/replace/english/rep1_l_english.yml",
    BOM + b'l_english:\r\n rep1_key: "Replace form one"\r\n',
)

# 12. Форма replace #2: localization/<lang>/replace/
_add(
    "replace_form2",
    "localization/english/replace/rep2_l_english.yml",
    BOM + b'l_english:\r\n rep2_key: "Replace form two"\r\n',
)

# 13. Заголовок с комментарием, отступы табами у записей
_add(
    "header_comment_tabs",
    "localization/english/tabs_l_english.yml",
    BOM
    + b'l_english: # header comment\r\n'
    + b'\ttab_key: "Tab indented"\r\n',
)

# 14. Многострочные значения: кавычка открыта на одной строке, закрыта ниже
_add(
    "multiline_values",
    "localization/english/multi_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' ml_first: "Line one of the story.\r\n'
    + b'\r\n'
    + b'Second paragraph of the same value.\r\n'
    + b'Third and final line."\r\n'
    + b' after_ml: "Normal value"\r\n'
    + b' ml_with_codes:0 "Intro @icon! text\r\n'
    + b'continues with [Character.GetName] here."\r\n'
    + b' ml_escaped: "He said \\"wait\\"\r\n'
    + b'and left."\r\n'
    + b' last_normal: "Done"\r\n',
)

# 15. Кавычка открыта и не закрыта до конца файла — не поглощать остаток
_add(
    "unterminated_to_eof",
    "localization/english/unterm_l_english.yml",
    BOM
    + b'l_english:\r\n'
    + b' good_before: "Fine"\r\n'
    + b' broken_key: "Opened but never closed\r\n'
    + b' another_line_without_quote\r\n',
)

# 16. Пустой файл и файл только с заголовком
_add("empty_file", "localization/english/empty_l_english.yml", b"")
_add(
    "header_only",
    "localization/english/honly_l_english.yml",
    BOM + b"l_english:\r\n",
)


def materialize(root: Path) -> list[Path]:
    """Записать корпус на диск как дерево фиктивного мода. Возвращает пути."""
    written = []
    for _name, (relpath, data) in SAMPLES.items():
        p = root / Path(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        written.append(p)
    return written
