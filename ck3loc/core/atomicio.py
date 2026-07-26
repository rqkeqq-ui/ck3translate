"""Атомарная запись файлов с резервной копией.

Правило проекта: сначала полностью пишем во временный файл, проверяем,
сохраняем копию старого, затем атомарно подменяем.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


def write_atomic(
    path: Path, data: bytes, backup_dir: Path | None = None
) -> Path | None:
    """Записать data в path атомарно.

    Если файл существовал и указан backup_dir — старая версия копируется
    туда с меткой времени. Возвращает путь резервной копии или None.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    backup_path: Path | None = None
    if path.exists() and backup_dir is not None:
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"{path.name}.{stamp}.bak"
        # не затираем предыдущий бэкап той же секунды
        n = 1
        while backup_path.exists():
            backup_path = backup_dir / f"{path.name}.{stamp}-{n}.bak"
            n += 1
        shutil.copy2(path, backup_path)

    tmp = path.with_name(path.name + ".ck3loc-tmp")
    tmp.write_bytes(data)
    # проверка: записанное читается и совпадает
    if tmp.read_bytes() != data:
        tmp.unlink(missing_ok=True)
        raise OSError(f"проверка записи не прошла: {path}")
    os.replace(tmp, path)
    return backup_path
