"""Сканер: языки, replace-формы, полнота, диагностика расхождений."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ck3loc.core.descriptor import Descriptor, render_descriptor
from ck3loc.core.scanner import (
    localization_fingerprint,
    scan_mod,
)
from tests.corpus import materialize


def make_fake_mod(root: Path) -> Path:
    """Фиктивный мод из синтетического корпуса + descriptor.mod."""
    mod_dir = root / "1234567890"
    materialize(mod_dir)
    (mod_dir / "descriptor.mod").write_text(
        render_descriptor(
            "Test Mod", "1.2", "1.16.*", tags=["Gameplay"],
        ),
        encoding="utf-8",
    )
    return mod_dir


class TestScanner(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.mod_dir = make_fake_mod(Path(self._td.name) / "Тест Мастерская")

    def tearDown(self):
        self._td.cleanup()

    def test_descriptor(self):
        d = Descriptor.load(self.mod_dir)
        self.assertTrue(d.exists)
        self.assertEqual(d.name, "Test Mod")
        self.assertEqual(d.version, "1.2")
        self.assertEqual(d.supported_version, "1.16.*")

    def test_languages_found(self):
        scan = scan_mod(self.mod_dir)
        self.assertIn("english", scan.languages)
        self.assertIn("russian", scan.languages)
        # файл mismatch лежит в russian, но заголовок l_english → english
        eng = scan.languages["english"]
        self.assertIn("mism_key", eng.keys)

    def test_replace_forms_scanned(self):
        scan = scan_mod(self.mod_dir)
        eng = scan.languages["english"]
        self.assertIn("rep1_key", eng.keys)  # localization/replace/english/
        self.assertIn("rep2_key", eng.keys)  # localization/english/replace/
        self.assertTrue(eng.keys["rep1_key"].replace_scope)
        self.assertTrue(eng.keys["rep2_key"].replace_scope)
        # вложенные папки тоже найдены
        self.assertIn("deep_key", eng.keys)

    def test_lang_mismatch_diagnosed(self):
        scan = scan_mod(self.mod_dir)
        codes = {d.code for _p, d in scan.diagnostics}
        self.assertIn("lang_mismatch", codes)

    def test_coverage_and_missing(self):
        scan = scan_mod(self.mod_dir)
        translated, of = scan.coverage("russian", "english")
        self.assertGreater(of, 10)
        self.assertEqual(translated, 0)  # русские ключи не пересекаются
        missing = scan.missing_keys("russian", "english")
        self.assertIn("greeting", missing)
        extra = scan.extra_keys("russian", "english")
        self.assertIn("холм", extra)

    def test_best_source_language(self):
        scan = scan_mod(self.mod_dir)
        self.assertEqual(scan.best_source_language("english"), "english")

    def test_fingerprint_stable_under_reordering(self):
        scan1 = scan_mod(self.mod_dir)
        fp1 = localization_fingerprint(scan1)
        # добавим комментарий и пустую строку в один файл — семантика та же
        f = self.mod_dir / "localization" / "english" / "lf_l_english.yml"
        data = f.read_bytes()
        f.write_bytes(data + b"# comment added\n\n")
        scan2 = scan_mod(self.mod_dir)
        self.assertEqual(fp1, localization_fingerprint(scan2))
        # а изменение значения отпечаток меняет
        f.write_bytes(data.replace(b'"Alpha"', b'"Changed"'))
        scan3 = scan_mod(self.mod_dir)
        self.assertNotEqual(fp1, localization_fingerprint(scan3))


if __name__ == "__main__":
    unittest.main()
