"""Скопировать локализации нескольких реальных модов в tests/fixtures/real/.

Исходные папки мастерской ТОЛЬКО читаются. Результат в git не попадает
(tests/fixtures/real/ в .gitignore) — корпус локальный для этой машины.

Запуск:  python tools/make_fixtures.py [--limit N]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ck3loc.core.steam import list_workshop_mod_dirs, workshop_content_dirs

DEST = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "real"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="сколько модов скопировать")
    args = ap.parse_args()

    content = workshop_content_dirs()
    if not content:
        print("Папка мастерской CK3 не найдена — фикстуры не созданы.")
        return 1
    mods = list_workshop_mod_dirs(content)
    copied = 0
    total_files = 0
    for mod_dir in mods:
        if copied >= args.limit:
            break
        loc = mod_dir / "localization"
        if not loc.is_dir():
            continue
        yml_files = list(loc.rglob("*.yml"))
        if not yml_files:
            continue
        dest = DEST / mod_dir.name / "localization"
        if dest.exists():
            shutil.rmtree(dest)
        for f in yml_files:
            rel = f.relative_to(loc)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            total_files += 1
        copied += 1
        print(f"  {mod_dir.name}: {len(yml_files)} файлов")
    print(f"Готово: {copied} модов, {total_files} файлов → {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
