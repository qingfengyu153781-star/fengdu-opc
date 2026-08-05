@echo off
chcp 65001 >nul
title 枫独 OPC 经营助手 - 投影高对比版（备用）
cd /d "%~dp0"

echo ============================================
echo  枫独 · OPC 经营助手  [投影高对比版]
echo  适用：决赛投影仪高光下，暖橙主题泛白看不清
echo  平时用「启动.bat」暖橙主版即可
echo ============================================
echo.

rem 检测 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python。请先安装 Python 3.9+。
    pause
    exit /b 1
)

rem 安装依赖（首次需联网）
echo [1/3] 检查依赖...
pip install -r requirements.txt -q 2>nul
echo 依赖就绪。

rem 启动前先开浏览器
start "" http://localhost:7860

echo [2/3] 启动服务（高对比主题）...
echo [3/3] 提示：关闭此窗口即停止服务。
echo.
set UI_THEME=high_contrast
python app.py

pause
