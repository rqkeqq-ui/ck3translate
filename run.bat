@echo off
chcp 65001 >nul
if not exist .venv (
    echo Сначала запустите install.bat
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
python -m ck3loc.desktop
