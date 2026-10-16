@echo off
chcp 65001 >nul
rem Сборка MacBookCam.exe. Результат: dist\MacBookCam.exe
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-pc.txt pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean MacBookCam-windows.spec
echo.
echo Готово: dist\MacBookCam.exe
pause
