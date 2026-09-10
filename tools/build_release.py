"""Build a native portable release; run on each target operating system."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ck3loc import __version__


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Release builds require Python 3.12. Use GitHub Actions or a Python 3.12 virtual environment.")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/validate_community_db.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "CK3LocalizationManager.spec"], cwd=ROOT, check=True)
    system = platform.system().lower()
    arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    dist = ROOT / "dist"
    package = dist / "CK3LocalizationManager"
    if system == "darwin":
        package = dist / "CK3LocalizationManager.app" / "Contents" / "Resources"
    executable = dist / "CK3LocalizationManager" / ("CK3LocalizationManager.exe" if system == "windows" else "CK3LocalizationManager")
    if system == "darwin":
        executable = dist / "CK3LocalizationManager.app" / "Contents" / "MacOS" / "CK3LocalizationManager"
    with tempfile.TemporaryDirectory() as temporary:
        data = Path(temporary)
        (data / "settings.json").write_text(json.dumps({
            "ui_lang": "en", "scan_on_start": False, "fetch_covers": False,
            "steam_path": str(data / "steam"), "community_db_enabled": False,
        }), encoding="utf-8")
        env = dict(os.environ, CK3LOC_DATA=temporary, CK3LOC_PDX_MOD_DIR=str(data / "mods"),
                   QT_QPA_PLATFORM="offscreen")
        try:
            subprocess.run([str(executable), "--smoke-test"], env=env, check=True, timeout=45)
        except (subprocess.SubprocessError, OSError):
            for log in data.glob("*.log"):
                print(log.read_text(encoding="utf-8", errors="replace"))
            raise
    for source, name in [("LICENSE", "LICENSE"), ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
                         ("README-запуск.md", "USER_GUIDE.md")]:
        shutil.copy2(ROOT / source, package / name)
    for distribution in importlib.metadata.distributions():
        for entry in distribution.files or []:
            if any(token in entry.name.lower() for token in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(entry))
                if source.is_file() and ".." not in entry.parts:
                    target = package / "THIRD_PARTY_LICENSES" / distribution.metadata["Name"] / str(entry)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    stem = dist / f"CK3LocalizationManager-{__version__}-{system}-{arch}"
    if system == "darwin":
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-",
                        str(dist / "CK3LocalizationManager.app")], check=True)
        archive = str(stem) + ".zip"
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(dist / "CK3LocalizationManager.app"), archive], check=True)
    else:
        archive = shutil.make_archive(str(stem), "zip" if system == "windows" else "gztar",
                                      root_dir=dist, base_dir="CK3LocalizationManager")
    path = Path(archive)
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    print(f"Release ready: {path.name}")


if __name__ == "__main__":
    main()
