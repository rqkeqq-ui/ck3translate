@echo off
chcp 65001 >nul
echo === CK3 Localization Manager: установка ===
where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python 3.12+ с python.org и запустите снова.
    pause
    exit /b 1
)
if not exist .venv (
    echo Создаю окружение...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Устанавливаю зависимости (может занять пару минут)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo ОШИБКА установки зависимостей. Проверьте интернет и запустите снова.
    pause
    exit /b 1
)
echo.
echo Готово! Запускайте приложение через run.bat
pause
