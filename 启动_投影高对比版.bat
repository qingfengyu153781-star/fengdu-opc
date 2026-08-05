@echo off
chcp 936
title FengDu High Contrast
cd /d "%~dp0"

echo ============================================
echo   FengDu High Contrast (Projector mode)
echo   Use this if warm theme looks washed out.
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

echo [2/3] Starting server (high contrast)...
echo [3/3] Close this window to stop.
echo.
set UI_THEME=high_contrast
python app.py
pause
