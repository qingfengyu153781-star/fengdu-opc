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

REM ==== 可选：配置 LLM API key（AI 语义理解/精准搜索词/合规问答深度增强）====
REM 取消下一行注释并填上你的 ModelScope key（https://modelscope.cn 免费获取）
REM set MODELSCOPE_API_KEY=ms-xxxxxxxx
REM ==== 可选：配置搜索 API（更稳定）====
REM set BING_SEARCH_API_KEY=your_bing_key
REM set SEARXNG_URL=http://127.0.0.1:8080

start "" http://localhost:7860

echo [2/3] Starting server...
echo [3/3] Close this window to stop the server.
echo.
python app.py
pause
