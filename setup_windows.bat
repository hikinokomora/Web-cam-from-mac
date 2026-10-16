@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python не найден. Установите с https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-pc.txt
echo.
echo Готово. Для запуска: start_windows.bat
pause
