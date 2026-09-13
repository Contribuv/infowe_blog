@echo off
rem ============================================================
rem  infowe-blog 一键重启脚本（Windows）
rem  用法：双击运行，或在 cmd 里执行 restart.bat
rem  作用：停掉占用 5000 端口的旧进程 → 后台重新拉起
rem  （仅适用于 python app.py 直跑、端口 5000 的部署方式）
rem ============================================================
setlocal
set "PORT=5000"
set "APP_DIR=%~dp0"

echo [1/2] 查找并停止占用 %PORT% 端口的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo   找到 PID %%a，正在停止...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [2/2] 启动新进程...
cd /d "%APP_DIR%"
if not exist logs mkdir logs
start "infowe-blog" /min cmd /c "python app.py >> logs\app.log 2>&1"

echo 重启完成。日志输出到 logs\app.log
endlocal