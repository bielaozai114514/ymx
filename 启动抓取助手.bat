@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [X] 没找到 Python。请先安装 Python 并勾选 Add Python to PATH。
  echo.
  pause
  exit /b
)

echo.
echo   ============================================
echo      ymx抓取助手  -  starting...
echo   ============================================
echo.
echo   它会让「ymx」网页能自动抓亚马逊商品数据。
echo   启动后回到网页，顶部会显示「抓取助手：已连接」。
echo.
echo   保持这个窗口开着；要停止，直接关掉它。
echo.
python fetcher.py

echo.
echo   抓取助手已停止。
pause
