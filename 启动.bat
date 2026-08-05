@echo off
chcp 65001 >nul
title 枫独 OPC 经营助手 - 启动中
cd /d "%~dp0"

echo ============================================
echo  枫独 · OPC 经营助手  正在启动...
echo ============================================
echo.

rem 检测 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python。
    echo 请先安装 Python 3.9+：https://www.python.org/downloads/
    echo 安装时勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

rem 安装依赖（首次需联网）
echo [1/3] 检查依赖...
pip install -r requirements.txt -q 2>nul
echo 依赖就绪。

rem 启动前先开浏览器（服务起来即可访问）
start "" http://localhost:7860

echo [2/3] 启动服务（浏览器会自动打开，请稍候）...
echo [3/3] 提示：关闭此窗口即停止服务。
echo.
python app.py

pause
