"""Главный тест ядра: read → parse → serialize == исходные байты.

Прогоняется на всём синтетическом корпусе и, если существует,
на tests/fixtures/real/ (копии локализаций реальных модов,
создаются скриптом tools/make_fixtures.py, в git не попадают).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ck3loc.core.locparser import LocFile
from tests.corpus import SAMPLES, materialize

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
REAL = FIXTURES / "real"


class TestRoundTripSynthetic(unittest.TestCase):
    def test_every_sample_roundtrips(self):
        for name, (_relpath, data) in SAMPLES.items():
            with self.subTest(sample=name):
                loc = LocFile.parse_bytes(data)
                self.assertEqual(
                    loc.to_bytes(),
                    data,
                    f"round-trip не байт-в-байт для образца {name}",
                )

    def test_roundtrip_from_disk(self):
        """То же самое через реальные файлы на диске (пути с кириллицей —
        сама папка проекта содержит кириллицу)."""
        materialize(SYNTHETIC)
        files = sorted(SYNTHETIC.rglob("*.yml"))
        self.assertGreater(len(files), 10, "корпус не материализовался")
        for f in files:
            with self.subTest(file=str(f)):
                data = f.read_bytes()
                self.assertEqual(LocFile.load(f).to_bytes(), data)

    def test_roundtrip_cyrillic_dir(self):
        """Явный тест юникодных путей: папка с кириллицей и пробелом."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "Тестовые Моды" / "локализация"
            d.mkdir(parents=True)
            p = d / "тест_l_russian.yml"
            data = b"\xef\xbb\xbf" + 'l_russian:\r\n k: "Значение"\r\n'.encode("utf-8")
            p.write_bytes(data)
            self.assertEqual(LocFile.load(p).to_bytes(), data)


class TestRoundTripReal(unittest.TestCase):
    def test_real_mods_roundtrip(self):
        if not REAL.exists():
            self.skipTest(
                "tests/fixtures/real отсутствует — запустите tools/make_fixtures.py"
            )
        files = sorted(REAL.rglob("*.yml"))
        if not files:
            self.skipTest("в tests/fixtures/real нет .yml файлов")
        for f in files:
            with self.subTest(file=str(f.relative_to(REAL))):
                data = f.read_bytes()
                self.assertEqual(LocFile.load(f).to_bytes(), data)


if __name__ == "__main__":
    unittest.main()
