"""Explicitly dispatched release action; never called by a build or tag push."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ck3loc import __version__


def main():
    tag = os.environ.get('RELEASE_TAG', '')
    if tag != 'v' + __version__:
        raise SystemExit('Release tag does not match the application version')
    commit = subprocess.check_output(['git','rev-parse',f'refs/tags/{tag}^{{commit}}'],text=True).strip()
    built = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if commit != built:
        raise SystemExit('Tag and built commit differ')
    assets = []
    for platform, suffix in [('windows-x86_64','zip'),('linux-x86_64','tar.gz'),('darwin-arm64','zip')]:
        path = Path('release-assets') / f'CK3LocalizationManager-{__version__}-{platform}.{suffix}'
        checksum = path.with_name(path.name+'.sha256')
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum.read_text(encoding='utf-8').strip() != f'{expected}  {path.name}':
            raise SystemExit(f'Checksum mismatch: {path}')
        assets.extend([str(path),str(checksum)])
    subprocess.run(['gh','release','create',tag,*assets,'--verify-tag','--draft','--title',
                    f'CK3 Localization Manager {tag}','--notes-file','.github/release-notes.md'],check=True)


if __name__ == '__main__':
    main()
