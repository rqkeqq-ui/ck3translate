"""Release regressions independent of the user's Steam installation."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ck3loc.core.steam import find_steam_root
from ck3loc.core.writer import pdx_mod_dir


class TestPlatformPaths(unittest.TestCase):
    def test_linux_and_mac_steam_locations(self):
        for suffix in (".local/share/Steam", ".steam/steam",
                       ".var/app/com.valvesoftware.Steam/.local/share/Steam",
                       "Library/Application Support/Steam"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                expected = Path(tmp) / suffix
                expected.mkdir(parents=True)
                with patch("pathlib.Path.home", return_value=Path(tmp)), \
                     patch.dict("sys.modules", {"winreg": None}), \
                     patch("pathlib.Path.exists", lambda p: p == expected):
                    self.assertEqual(find_steam_root(), expected)

    def test_linux_patch_path_and_override(self):
        with patch("ck3loc.core.writer.sys.platform", "linux"), \
             patch.dict(os.environ, {}, clear=True), \
             patch("pathlib.Path.home", return_value=Path("/demo")):
            self.assertEqual(pdx_mod_dir(), Path("/demo/.local/share/Paradox Interactive/Crusader Kings III/mod"))
            with patch.dict(os.environ, {"CK3LOC_PDX_MOD_DIR": "/custom"}):
                self.assertEqual(pdx_mod_dir(), Path("/custom"))
