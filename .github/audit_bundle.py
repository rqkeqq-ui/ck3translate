"""Reject local development/data payloads in native bundles and their PYZ."""
from __future__ import annotations
from pathlib import Path
import tempfile
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

FORBIDDEN = {'tests','tools','workshop','.git','.venv','venv','.ck3loc-data'}


def audit_bundle(package: Path, executable: Path) -> None:
    for path in package.rglob('*'):
        parts = {p.casefold() for p in path.relative_to(package).parts}
        if parts & FORBIDDEN or path.name in {'AGENTS.md','NEXT_RELEASE_030_PLAN.md'} or path.suffix in {'.sqlite3','.log'}:
            raise RuntimeError(f'Development/user payload in bundle: {path}')
    archive = CArchiveReader(str(executable))
    for name in archive.toc:
        if name.startswith('PYZ'):
            with tempfile.TemporaryDirectory() as directory:
                pyz = Path(directory)/'modules.pyz'
                pyz.write_bytes(archive.extract(name))
                modules = ZlibArchiveReader(str(pyz)).toc
                bad = [m for m in modules if m.split('.')[0].casefold() in FORBIDDEN]
                if bad:
                    raise RuntimeError(f'Development modules in PYZ: {bad}')
