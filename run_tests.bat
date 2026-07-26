@echo off
if exist .venv call .venv\Scripts\activate.bat
python tools\run_tests.py
pause
