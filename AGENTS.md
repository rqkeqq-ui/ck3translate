# Repository Guidelines

## Project Structure & Module Organization

`ck3loc/` is the application package. Put domain logic in `ck3loc/core/`, command-line behavior in `ck3loc/cli/`, PySide6 UI code in `ck3loc/desktop/`, and translation-service integrations in `ck3loc/providers/`. Interface dictionaries live in `ck3loc/lang/*.json`. Tests mirror features under `tests/test_*.py`; reusable localization samples belong in `tests/fixtures/synthetic/`. Maintenance scripts are kept in `tools/`. Treat `CK3-Localization-Manager-Spec.md` as the product reference and `README-запуск.md` as the user-facing operating guide.

## Build, Test, and Development Commands

- `install.bat` creates `.venv` and installs `requirements.txt` on Windows.
- `run.bat` launches the desktop application, installing missing dependencies if needed.
- `python -m ck3loc.desktop` starts the GUI from an activated environment.
- `python -m ck3loc scan` exercises the CLI and scans the local CK3 library.
- `run_tests.bat` runs the complete test suite.
- `python -m unittest discover -s tests -v` runs the same suite with verbose output.
- `python -m unittest tests.test_parser` runs one test module during development.

There is no separate compile step; use Python 3.12 or newer.

## Coding Style & Naming Conventions

Use four-space indentation and conventional PEP 8 naming: `snake_case` for modules, functions, and variables; `PascalCase` for classes; `UPPER_CASE` for constants. Keep `from __future__ import annotations` in typed modules and add type hints to public APIs. Prefer small domain-focused functions, `pathlib.Path`, and UTF-8 for text. Preserve CK3 localization bytes, BOMs, line endings, and tokens through the parser/writer abstractions rather than editing files as generic YAML. No formatter or linter is configured, so match nearby code and keep imports grouped.

## Testing Guidelines

Tests use the standard-library `unittest` framework. Name files `test_<feature>.py`, classes `Test<Behavior>`, and methods `test_<expected_result>`. Add regression coverage for parser round trips, token preservation, database migrations, and GUI behavior affected by a change. Use temporary directories and `CK3LOC_DATA`/`CK3LOC_PDX_MOD_DIR` overrides; never depend on a contributor's live Steam library. GUI tests may skip when PySide6 is unavailable.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style prefixes such as `feat:`, `fix:`, and `design:` with concise Russian summaries. Keep each commit scoped to one logical change. Pull requests should explain behavior and user impact, list tests run, link related issues, and include before/after screenshots for visible UI changes. Call out schema, localization-format, or provider/API changes explicitly.

## Security & Local Data

Never commit API keys, real workshop fixtures, `.ck3loc-data/`, logs, or virtual environments. Store provider secrets through the application's keyring support. Use `write --dry-run` before testing changes that could modify installed mods.
