@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [1/2] 创建虚拟环境...
    python -m venv .venv
    echo [2/2] 安装依赖...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
.venv\Scripts\python.exe app.py
pause
