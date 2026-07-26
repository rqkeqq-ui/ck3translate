"""Прогон всех тестов с русским итогом (вызывается из run_tests.bat)."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
proc = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
    cwd=root,
)
print()
if proc.returncode == 0:
    print("=== ВСЕ ТЕСТЫ ПРОЙДЕНЫ ===")
else:
    print("=== ЕСТЬ УПАВШИЕ ТЕСТЫ ===")
    print("Подробности: python -m unittest discover -s tests -v")
sys.exit(proc.returncode)
