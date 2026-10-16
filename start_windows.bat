@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Сначала запустите setup_windows.bat & pause & exit /b 1)
.venv\Scripts\python.exe pc_receiver.py %*
pause
