@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [X] 没找到 Python。
  echo   请先安装 Python（安装时勾选 Add Python to PATH）。
  echo   或者：直接双击 index.html 也能用「算利润」，只是「问 AI」可能受浏览器限制。
  echo.
  pause
  exit /b
)

echo.
echo   ============================================
echo      ymx - 亚马逊选品闭环工作台  正在启动...
echo   ============================================
echo.
echo   浏览器会自动打开：http://127.0.0.1:8770/index.html
echo.
echo   要停止服务：关闭那个标题为 "suanpan" 的最小化窗口。
echo.
start "suanpan" /min cmd /c "python -m http.server 8770 --bind 127.0.0.1"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8770/index.html"
echo   已启动。
echo.
pause
