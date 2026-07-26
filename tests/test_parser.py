"""Семантика парсера: ключи, значения, статусы строк, редактирование."""

from __future__ import annotations

import unittest

from ck3loc.core.locparser import (
    BOM,
    ENTRY,
    HEADER,
    UNKNOWN,
    LocFile,
    build_new_file,
    decode_value,
    encode_value,
)
from tests.corpus import SAMPLES


def sample(name: str) -> bytes:
    return SAMPLES[name][1]


class TestParsing(unittest.TestCase):
    def test_basic_entries(self):
        loc = LocFile.parse_bytes(sample("basic_crlf_bom"))
        self.assertEqual(loc.header_lang, "english")
        self.assertTrue(loc.had_bom)
        entries = {e.key: e for e in loc.entries()}
        self.assertEqual(
            set(entries), {"greeting", "old_style", "numbered", "trailing"}
        )
        self.assertEqual(entries["greeting"].value, "Hello, world")
        self.assertEqual(entries["greeting"].number, "")
        self.assertEqual(entries["old_style"].number, "0")
        self.assertEqual(entries["numbered"].number, "15")
        # хвостовой комментарий не входит в значение
        self.assertEqual(entries["trailing"].value, "Value")

    def test_escapes_decoded(self):
        loc = LocFile.parse_bytes(sample("codes_and_escapes"))
        e = loc.get("quoted")
        self.assertEqual(e.value, 'He said "stop" twice')
        # литеральный \n остаётся двумя символами
        self.assertEqual(loc.get("newline").value, "First line\\nSecond line")
        # вложенные кавычки внутри [...] сохраняются
        self.assertIn("Concept('realm','Realm')", loc.get("nested").value)

    def test_broken_lines_are_unknown_not_fatal(self):
        loc = LocFile.parse_bytes(sample("broken_lines"))
        kinds = [l.kind for l in loc.lines]
        self.assertIn(UNKNOWN, kinds)
        self.assertIsNotNone(loc.get("good_key"))
        codes = {d.code for d in loc.diagnostics()}
        self.assertIn("unparsed_line", codes)

    def test_duplicate_keys_diagnosed(self):
        loc = LocFile.parse_bytes(sample("duplicate_keys"))
        codes = [d.code for d in loc.diagnostics()]
        self.assertIn("duplicate_key", codes)
        # оба вхождения доступны
        occurrences = [e for e in loc.entries() if e.key == "same_key"]
        self.assertEqual(len(occurrences), 2)
        self.assertEqual([o.value for o in occurrences], ["First", "Second"])

    def test_invalid_utf8_line_isolated(self):
        loc = LocFile.parse_bytes(sample("invalid_utf8"))
        self.assertIsNotNone(loc.get("ok_key"))
        self.assertIsNotNone(loc.get("after_key"))
        bad = [l for l in loc.lines if not l.decode_ok]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].kind, UNKNOWN)
        with self.assertRaises(ValueError):
            bad[0].set_value("нельзя")

    def test_header_mismatch_detected_via_header_lang(self):
        loc = LocFile.parse_bytes(sample("path_mismatch"))
        # файл лежит в russian, но язык по заголовку — english
        self.assertEqual(loc.header_lang, "english")


class TestEditing(unittest.TestCase):
    def test_set_value_changes_only_value(self):
        data = sample("basic_crlf_bom")
        loc = LocFile.parse_bytes(data)
        loc.get("greeting").set_value("Привет, мир")
        out = loc.to_bytes()
        self.assertNotEqual(out, data)
        # перечитываем результат: значение изменилось, остальное на месте
        loc2 = LocFile.parse_bytes(out)
        self.assertEqual(loc2.get("greeting").value, "Привет, мир")
        self.assertEqual(loc2.get("old_style").value, "Zero style")
        self.assertEqual(loc2.get("old_style").number, "0")
        self.assertTrue(out.startswith(BOM))
        # трейлинг-комментарий у другой строки не пострадал
        self.assertIn(b"# trailing comment", out)
        # если вернуть исходное значение той же строкой — байты совпадают
        loc3 = LocFile.parse_bytes(data)
        loc3.get("greeting").set_value("Hello, world")
        self.assertEqual(loc3.to_bytes(), data)

    def test_quotes_escaped_on_write(self):
        loc = LocFile.parse_bytes(sample("lf_nobom"))
        loc.get("key_a").set_value('Он сказал "стоп"')
        out = loc.to_bytes()
        loc2 = LocFile.parse_bytes(out)
        self.assertEqual(loc2.get("key_a").value, 'Он сказал "стоп"')
        # в сыром виде кавычки экранированы
        self.assertIn(b'\\"', out)

    def test_eol_preserved_per_line(self):
        data = sample("mixed_eol")
        loc = LocFile.parse_bytes(data)
        loc.get("crlf_key").set_value("Изменено")
        out = loc.to_bytes()
        # CRLF у изменённой строки сохранился, LF у соседней тоже
        self.assertIn("Изменено".encode("utf-8") + b'"\r\n', out)
        self.assertIn(b'lf_key: "LF line"\n', out)
        # последняя строка по-прежнему без перевода строки
        self.assertFalse(out.endswith(b"\n"))

    def test_encode_decode_value(self):
        self.assertEqual(decode_value('a \\"b\\"'), 'a "b"')
        self.assertEqual(encode_value('a "b"'), 'a \\"b\\"')
        # уже экранированное не задваивается
        self.assertEqual(encode_value('a \\"b\\"'), 'a \\"b\\"')


class TestBuildNewFile(unittest.TestCase):
    def test_new_file_valid(self):
        data = build_new_file("russian", [("k1", "Один"), ("k2", 'Ци "тата"')])
        self.assertTrue(data.startswith(BOM))
        self.assertIn(b"\r\n", data)
        loc = LocFile.parse_bytes(data)
        self.assertEqual(loc.header_lang, "russian")
        self.assertEqual(loc.get("k1").value, "Один")
        self.assertEqual(loc.get("k2").value, 'Ци "тата"')
        # round-trip нового файла тоже байт-в-байт
        self.assertEqual(loc.to_bytes(), data)


if __name__ == "__main__":
    unittest.main()
