@echo off
setlocal
cd /d "%~dp0"

rem 1) virtualenv if present, otherwise system python
if exist ".venv\Scripts\pythonw.exe" (
    set "PYW=.venv\Scripts\pythonw.exe"
    set "PY=.venv\Scripts\python.exe"
) else (
    where pythonw >nul 2>nul || goto :nopython
    set "PYW=pythonw"
    set "PY=python"
)

rem 2) verify dependencies, install them once if missing
"%PY%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies, this happens only once...
    "%PY%" -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Could not install dependencies. Run install.bat and read the messages.
        pause
        exit /b 1
    )
)

start "" "%PYW%" -m ck3loc.desktop
exit /b 0

:nopython
echo Python not found. Install Python 3.12+ from python.org
echo and tick "Add Python to PATH" during setup.
pause
exit /b 1
