@echo off
echo === CK3 Localization Manager: installation ===
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.12+ from python.org and re-run.
    pause
    exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
echo Installing dependencies, this may take a few minutes...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo INSTALL ERROR. Check the internet connection and re-run.
    pause
    exit /b 1
)
echo.
echo Done! Start the app with run.bat
pause
