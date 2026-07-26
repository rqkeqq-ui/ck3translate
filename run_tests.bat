@echo off
chcp 65001 >nul
if exist .venv (
    call .venv\Scripts\activate.bat
)
python -m unittest discover -s tests -v 2>&1 | findstr /R /C:"^Ran" /C:"^OK" /C:"^FAILED" /C:"^ERROR"
python -m unittest discover -s tests >nul 2>&1
if errorlevel 1 (
    echo.
    echo === ЕСТЬ УПАВШИЕ ТЕСТЫ — подробности: python -m unittest discover -s tests -v ===
) else (
    echo.
    echo === ВСЕ ТЕСТЫ ПРОЙДЕНЫ ===
)
pause
