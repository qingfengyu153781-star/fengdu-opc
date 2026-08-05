@echo off
chcp 936
title FengDu OPC Assistant
cd /d "%~dp0"

echo ============================================
echo   FengDu OPC Assistant
echo   Starting demo server...
echo ============================================
echo.

where python
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.9+ first.
    pause
    exit /b 1
)

echo [1/3] Checking dependencies...
pip install -r requirements.txt -q
echo Dependencies OK.

start "" http://localhost:7860

echo [2/3] Starting server...
echo [3/3] Close this window to stop the server.
echo.
python app.py
pause
