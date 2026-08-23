"""Проверить staging-каталог Community Database перед загрузкой в Steam."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from ck3loc.core.community_db import CommunityDatabaseError, load_community_database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=ROOT / "workshop" / "ck3loc_community_database",
    )
    args = parser.parse_args()
    try:
        database = load_community_database(args.path)
    except CommunityDatabaseError as exc:
        print(f"ОШИБКА: {exc}")
        return 1
    print(f"База корректна: {database.database_version}")
    print(f"Терминов: {len(database.glossaries)}")
    print(f"Связей русификаторов: {len(database.translations)}")
    print(f"Правил модов: {len(database.mod_rules)}")
    for warning in database.warnings:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
