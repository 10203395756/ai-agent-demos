@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ============================================================
echo  AI Agent Demo - Windows 一键启动脚本
echo ============================================================
echo.

REM ========== 1. 检测 Python ==========
set PY=
where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY=py -3
    ) else (
        where python3 >nul 2>nul
        if %errorlevel%==0 set PY=python3
    )
)

if "%PY%"=="" (
    echo [错误] 没找到 Python！请先安装 Python 3.9+
    echo        下载地址：https://www.python.org/downloads/
    echo        安装时记得勾选 "Add Python to PATH"
    pause
    exit /b 1
)
echo [1/5] 检测到 Python: %PY%
%PY% --version

REM ========== 2. 检测虚拟环境 ==========
if not exist ".venv" (
    echo.
    echo [2/5] 第一次运行，正在创建虚拟环境 .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [警告] 创建虚拟环境失败，尝试直接用系统 Python
    )
) else (
    echo [2/5] 检测到已存在虚拟环境 .venv
)

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    set PY=python
    echo        已激活虚拟环境
)

REM ========== 3. 安装依赖 ==========
echo.
echo [3/5] 检查并安装依赖 ...
%PY% -c "import fastapi, langchain, langgraph, multipart" >nul 2>nul
if errorlevel 1 (
    echo        正在安装依赖（首次需要联网，可能需要1-3分钟）...
    %PY% -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
    if exist "requirements-lite.txt" (
        %PY% -m pip install -r requirements-lite.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    ) else (
        %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    )
    if errorlevel 1 (
        echo.
        echo [警告] pip 安装失败（可能无网络）
        echo        你仍可以先运行零依赖验证：%PY% verify_quick.py
        echo        确认联网后重新运行本脚本即可自动安装。
        echo.
        pause
    )
) else (
    echo        依赖已安装，跳过。
)

REM ========== 4. 初始化数据（首次） ==========
if not exist "data\vector_db" (
    echo.
    echo [4/5] 初始化示例数据 ...
    %PY% init_data.py >nul 2>nul
) else (
    echo [4/5] 示例数据已存在，跳过。
)

REM ========== 5. 启动服务 ==========
echo.
echo [5/5] 启动服务（Mock 模式，无需 API Key）
echo ============================================================
echo  API 文档：http://localhost:8000/docs
echo  健康检查：http://localhost:8000/health
echo  监控指标：http://localhost:8000/metrics
echo  按 Ctrl+C 停止服务
echo ============================================================
echo.

%PY% main.py

if errorlevel 1 (
    echo.
    echo [错误] 服务启动失败，请先运行 %PY% verify_quick.py 验证环境
    pause
)
