"""GUI bootstrap with startup diagnostics for windowed bundles."""
from __future__ import annotations

import traceback

try:
    from ck3loc.desktop.app import main

    result = main()
except Exception:
    from ck3loc.core.db import data_dir

    (data_dir() / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    raise
raise SystemExit(result)
