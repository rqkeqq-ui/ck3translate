@echo off
if not exist .venv (
    echo Run install.bat first
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
start "" pythonw -m ck3loc.desktop
