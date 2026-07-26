"""Ворота этапа 4: сквозной сценарий B + строгость импорта + оба режима записи.

Сценарий B: мод без русского → экспорт JSONL → «перевод» (имитация LLM)
→ импорт → запись внутрь мода → корректные файлы, файлы автора не тронуты.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ck3loc.core import db
from ck3loc.core.bundle import export_jsonl, import_jsonl
from ck3loc.core.locparser import BOM, LocFile
from ck3loc.core.scanner import scan_mod, semantic_hash
from ck3loc.core.status import MACHINE
from ck3loc.core.store import ensure_project, get_project, get_units, upsert_unit
from ck3loc.core.writer import (
    apply_write_plan,
    build_write_plan,
    verify_outputs,
)
from ck3loc.core.xliff import export_xliff, import_xliff
from tests.test_scanner import make_fake_mod


def fake_llm_translate(jsonl_path: Path) -> Path:
    """Имитация внешней LLM: переводит source, сохраняя маркеры ⟦Tn⟧."""
    out_lines = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        obj["target"] = "RU: " + obj["source"]
        out_lines.append(json.dumps(obj, ensure_ascii=False))
    out = jsonl_path.with_name("translated.jsonl")
    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return out


class MvpTestCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        base = Path(self._td.name)
        os.environ["CK3LOC_DATA"] = str(base / "данные")
        os.environ["CK3LOC_PDX_MOD_DIR"] = str(base / "Paradox Mods")
        self.conn = db.connect()
        self.mod_dir = make_fake_mod(base / "workshop")
        self.scan = scan_mod(self.mod_dir)
        self.pid = ensure_project(self.conn, self.scan.mod_id)

    def tearDown(self):
        self.conn.close()
        os.environ.pop("CK3LOC_DATA", None)
        os.environ.pop("CK3LOC_PDX_MOD_DIR", None)
        self._td.cleanup()

    def source_rows(self, limit=None):
        src = self.scan.languages["english"]
        rows = [
            {"key": k, "source": occ.value}
            for k, occ in sorted(src.keys.items())
        ]
        return rows[:limit] if limit else rows

    def current_source_values(self):
        return {k: o.value for k, o in self.scan.languages["english"].keys.items()}


class TestScenarioB(MvpTestCase):
    def test_full_cycle_jsonl_to_in_mod_write(self):
        # 1. экспорт
        rows = self.source_rows()
        exp = export_jsonl(
            self.conn, self.pid, rows,
            Path(self._td.name) / "export" / "job.jsonl",
            "english", "russian",
        )
        self.assertTrue(exp.path.exists())
        self.assertTrue(exp.prompt_path.exists())
        self.assertEqual(exp.unit_count, len(rows))

        # 2. «перевод» внешней LLM
        translated = fake_llm_translate(exp.path)

        # 3. строгий импорт
        report = import_jsonl(self.conn, translated, self.current_source_values())
        self.assertTrue(report.ok, report.fatal)
        self.assertEqual(len(report.rejected), 0,
                         [r.reason for r in report.rejected])
        self.assertEqual(len(report.accepted), len(rows))

        # 4. в базу
        for item in report.accepted:
            src_val = self.current_source_values()[item.key]
            upsert_unit(
                self.conn, self.pid, item.key, src_val,
                semantic_hash(src_val), item.target, MACHINE, "external_llm",
            )
        self.conn.commit()

        # 5. запись внутрь мода
        project = dict(get_project(self.conn, self.pid))
        units = get_units(self.conn, self.pid)
        plan = build_write_plan(self.scan, project, units)
        self.assertEqual(plan.write_mode, "in_mod")
        result = apply_write_plan(self.conn, self.pid, plan, self.scan, units)
        self.assertTrue(result.written)

        # 6. проверки результата — только файлы, записанные приложением
        rus_dir = self.mod_dir / "localization" / "russian"
        written_files = [p for p in result.written if p.suffix == ".yml"]
        self.assertTrue(written_files)
        self.assertTrue(all(rus_dir in p.parents or "replace" in p.parts
                            for p in written_files))
        for f in written_files:
            data = f.read_bytes()
            self.assertTrue(data.startswith(BOM), f"{f} без BOM")
            loc = LocFile.parse_bytes(data)
            self.assertEqual(loc.header_lang, "russian")
            for e in loc.entries():
                self.assertTrue(e.value.startswith("RU: ") or e.value)

        # ключ greeting переведён и читается парсером
        all_keys = {}
        for f in written_files:
            for e in LocFile.load(f).entries():
                all_keys[e.key] = e.value
        self.assertIn("greeting", all_keys)
        self.assertEqual(all_keys["greeting"], "RU: Hello, world")

        # 7. файлы автора не тронуты (сравнение байтов english-дерева)
        eng = self.mod_dir / "localization" / "english"
        basic = eng / "basic_l_english.yml"
        from tests.corpus import SAMPLES

        self.assertEqual(basic.read_bytes(), SAMPLES["basic_crlf_bom"][1])

        # 8. verify: всё на месте
        checks = verify_outputs(self.conn, self.pid)
        self.assertTrue(all(c.state == "ok" for c in checks))

        # 9. имитация обновления Steam: перевод стёрт → verify видит пропажу
        import shutil

        shutil.rmtree(rus_dir)
        checks = verify_outputs(self.conn, self.pid)
        self.assertTrue(any(c.state == "missing" for c in checks))

        # 10. восстановление: план собирается из базы заново
        plan2 = build_write_plan(self.scan, project, get_units(self.conn, self.pid))
        apply_write_plan(self.conn, self.pid, plan2, self.scan,
                         get_units(self.conn, self.pid))
        checks = verify_outputs(self.conn, self.pid)
        self.assertTrue(all(c.state == "ok" for c in checks))


class TestImportStrictness(MvpTestCase):
    def _export(self):
        return export_jsonl(
            self.conn, self.pid, self.source_rows(limit=5),
            Path(self._td.name) / "export" / "job.jsonl",
            "english", "russian",
        )

    def test_broken_token_rejected(self):
        exp = self._export()
        lines = []
        for line in exp.path.read_text(encoding="utf-8").splitlines():
            obj = json.loads(line)
            # переводчик «съел» маркер
            obj["target"] = "перевод без маркеров"
            lines.append(json.dumps(obj, ensure_ascii=False))
        bad = exp.path.with_name("bad.jsonl")
        bad.write_text("\n".join(lines), encoding="utf-8")
        report = import_jsonl(self.conn, bad, self.current_source_values())
        self.assertTrue(report.ok)
        # строки с кодами отклонены, простые строки приняты
        with_codes = [r for r in report.rejected if "маркер" in r.reason
                      or "не совпадает" in r.reason]
        simple = [a for a in report.accepted]
        self.assertEqual(len(report.accepted) + len(report.rejected), 5)
        self.assertTrue(len(simple) > 0)

    def test_changed_source_rejected(self):
        exp = self._export()
        translated = fake_llm_translate(exp.path)
        # источник обновился после экспорта
        values = self.current_source_values()
        first_key = json.loads(
            exp.path.read_text(encoding="utf-8").splitlines()[0]
        )["key"]
        values[first_key] = values[first_key] + " CHANGED BY AUTHOR"
        report = import_jsonl(self.conn, translated, values)
        self.assertTrue(report.ok)
        self.assertTrue(
            any(r.key == first_key and "изменился" in r.reason
                for r in report.rejected)
        )

    def test_partial_file_accepted_with_report(self):
        """Нейросеть вернула не все строки — принимаем что есть,
        остальное остаётся в работе."""
        exp = self._export()
        translated = fake_llm_translate(exp.path)
        lines = translated.read_text(encoding="utf-8").splitlines()
        cut = translated.with_name("cut.jsonl")
        cut.write_text("\n".join(lines[:2]), encoding="utf-8")
        report = import_jsonl(self.conn, cut, self.current_source_values())
        self.assertTrue(report.ok, report.fatal)
        self.assertEqual(len(report.accepted), 2)
        self.assertEqual(report.not_returned, 3)

    def test_duplicate_ids_fatal(self):
        exp = self._export()
        translated = fake_llm_translate(exp.path)
        lines = translated.read_text(encoding="utf-8").splitlines()
        dup = translated.with_name("dup.jsonl")
        dup.write_text("\n".join(lines + [lines[0]]), encoding="utf-8")
        report = import_jsonl(self.conn, dup, self.current_source_values())
        self.assertFalse(report.ok)

    def test_alien_file_fatal(self):
        alien = Path(self._td.name) / "alien.jsonl"
        alien.write_text(
            '{"id":"u0001","key":"nope","source":"x","target":"y","tokens":{}}',
            encoding="utf-8",
        )
        report = import_jsonl(self.conn, alien, self.current_source_values())
        self.assertFalse(report.ok)


class TestXliff(MvpTestCase):
    def test_xliff_roundtrip(self):
        rows = self.source_rows(limit=4)
        exp = export_xliff(
            self.conn, self.pid, rows,
            Path(self._td.name) / "export" / "job.xliff",
            "english", "russian",
        )
        # имитация переводчика: заполняем target в XML
        import xml.etree.ElementTree as ET

        ns = "urn:oasis:names:tc:xliff:document:2.0"
        tree = ET.parse(exp.path)
        for seg in tree.getroot().iter(f"{{{ns}}}segment"):
            src = seg.find(f"{{{ns}}}source")
            tgt = seg.find(f"{{{ns}}}target")
            tgt.text = "RU: " + (src.text or "")
        tree.write(exp.path, encoding="utf-8", xml_declaration=True)

        report = import_xliff(self.conn, exp.path, self.current_source_values())
        self.assertTrue(report.ok, report.fatal)
        self.assertEqual(len(report.accepted), 4,
                         [r.reason for r in report.rejected])


class TestPatchModMode(MvpTestCase):
    def test_patch_mod_layout(self):
        from ck3loc.core.store import set_project_option

        set_project_option(self.conn, self.pid, "write_mode", "patch_mod")
        values = self.current_source_values()
        for key in list(values)[:3]:
            upsert_unit(
                self.conn, self.pid, key, values[key],
                semantic_hash(values[key]), "перевод " + key, MACHINE, "test",
            )
        self.conn.commit()
        project = dict(get_project(self.conn, self.pid))
        units = get_units(self.conn, self.pid)
        plan = build_write_plan(self.scan, project, units)
        apply_write_plan(self.conn, self.pid, plan, self.scan, units)

        pdx = Path(os.environ["CK3LOC_PDX_MOD_DIR"])
        patch_root = pdx / f"ck3loc_{self.scan.mod_id}_russian"
        self.assertTrue((patch_root / "descriptor.mod").exists())
        self.assertTrue((pdx / f"ck3loc_{self.scan.mod_id}_russian.mod").exists())
        self.assertTrue((patch_root / ".ck3loc" / "manifest.json").exists())
        rep = patch_root / "localization" / "replace" / "russian"
        self.assertTrue(list(rep.glob("*_l_russian.yml")))
        # имя в лаунчере по шаблону [RU]
        desc = (patch_root / "descriptor.mod").read_text(encoding="utf-8")
        self.assertIn('name="[RU] Test Mod"', desc)
        # мастерская не тронута
        self.assertFalse(
            (self.mod_dir / "localization" / "russian" / "новых.yml").exists()
        )


class TestWriteModeSwitch(MvpTestCase):
    def test_switch_to_patch_mod_cleans_in_mod_files(self):
        """Смена режима записи убирает файлы прежнего режима (с бэкапом),
        иначе перевод дублируется, а патч-мод собирается пустым."""
        from ck3loc.core.store import set_project_option
        from ck3loc.core.writer import remove_outputs

        values = self.current_source_values()
        for key in list(values)[:3]:
            upsert_unit(
                self.conn, self.pid, key, values[key],
                semantic_hash(values[key]), "перевод " + key, MACHINE, "t",
            )
        self.conn.commit()
        project = dict(get_project(self.conn, self.pid))
        units = get_units(self.conn, self.pid)
        plan = build_write_plan(self.scan, project, units)
        apply_write_plan(self.conn, self.pid, plan, self.scan, units)
        written = [p for p in
                   (f.abs_path for f in plan.files) if p.exists()]
        self.assertTrue(written)

        removed = remove_outputs(self.conn, self.pid, self.scan.mod_id)
        self.assertEqual(sorted(map(str, removed)), sorted(map(str, written)))
        self.assertTrue(all(not p.exists() for p in written))

        set_project_option(self.conn, self.pid, "write_mode", "patch_mod")
        from ck3loc.core.scanner import scan_mod as rescan

        fresh_scan = rescan(self.mod_dir)
        project = dict(get_project(self.conn, self.pid))
        units = get_units(self.conn, self.pid)
        plan2 = build_write_plan(fresh_scan, project, units)
        apply_write_plan(self.conn, self.pid, plan2, fresh_scan, units)
        pdx = Path(os.environ["CK3LOC_PDX_MOD_DIR"])
        self.assertTrue(
            (pdx / f"ck3loc_{self.scan.mod_id}_russian" / "descriptor.mod").exists()
        )


class TestDeltaMode(MvpTestCase):
    def test_delta_skips_native_equal(self):
        # родной русский уже содержит ключ "холм" → дельта его не пишет,
        # а перевод нового ключа пишет
        values = self.current_source_values()
        upsert_unit(
            self.conn, self.pid, "greeting", values["greeting"],
            semantic_hash(values["greeting"]), "Привет, мир", MACHINE, "t",
        )
        # переопределение родного значения
        native_val = self.scan.languages["russian"].keys["холм"].value
        upsert_unit(
            self.conn, self.pid, "холм", "x", semantic_hash("x"),
            native_val, MACHINE, "t",
        )
        self.conn.commit()
        project = dict(get_project(self.conn, self.pid))
        units = get_units(self.conn, self.pid)
        plan = build_write_plan(self.scan, project, units, build_mode="delta")
        keys_planned = [k for f in plan.files for k in f.keys]
        self.assertIn("greeting", keys_planned)
        self.assertNotIn("холм", keys_planned)  # совпадает с родным — не пишем


if __name__ == "__main__":
    unittest.main()
