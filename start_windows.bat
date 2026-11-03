@echo off
chcp 65001 >nul
REM ============================================================
REM  AI 智能体平台 - Windows 一键启动脚本
REM  用法：双击本文件，或在 cmd 中执行  start_windows.bat
REM  设计原则：优先复用已装依赖；无网络也能跑 Mock 模式
REM ============================================================
cd /d "%~dp0"

echo ========================================
echo  AI 智能体平台 一键启动 (Windows)
echo ========================================
echo.

REM ---------- 1. 定位 Python 解释器 ----------
REM Windows 上是 python / py，不是 python3
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo [X] 未检测到 Python。请先安装 Python 3.10+ 并勾选 "Add to PATH"
    echo     下载地址: https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [√] 解释器: %PY%  ^(%PYVER%^)
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>nul
if errorlevel 1 (
    echo [X] Python 版本过低，需要 3.10 及以上
    pause
    exit /b 1
)
echo.

REM ---------- 2. 准备 .env ----------
if not exist ".env" (
    echo [i] 未找到 .env，正在从 .env.example 复制（默认 Mock 模式，无需 API Key）
    copy /y ".env.example" ".env" >nul
)
echo [√] 配置文件 .env 就绪
echo.

REM ---------- 3. 检查核心依赖 ----------
echo [..] 检查核心依赖...
set "MISSING="
%PY% -c "import importlib.util as u,sys; mods=['langchain_core','langchain','langgraph','fastapi','uvicorn','pydantic','pydantic_settings','slowapi','prometheus_client','structlog','sse_starlette','chromadb','multipart']; m=[x for x in mods if u.find_spec(x) is None]; sys.stdout.write(' '.join(m))" > "%TEMP%\_aadep.txt" 2>nul
set /p MISSING=<"%TEMP%\_aadep.txt"
del "%TEMP%\_aadep.txt" >nul 2>nul

if not "%MISSING%"=="" (
    echo [!] 缺少依赖: %MISSING%
    echo [..] 尝试从清华镜像安装...
    %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    if errorlevel 1 (
        echo [..] 镜像安装失败，尝试默认源...
        %PY% -m pip install -r requirements.txt --quiet
    )
    REM 重新检查
    %PY% -c "import importlib.util as u,sys; mods=['langchain_core','langchain','langgraph','fastapi','uvicorn','pydantic','pydantic_settings','slowapi','prometheus_client','structlog','sse_starlette','chromadb','multipart']; m=[x for x in mods if u.find_spec(x) is None]; sys.stdout.write(' '.join(m))" > "%TEMP%\_aadep.txt" 2>nul
    set /p MISSING=<"%TEMP%\_aadep.txt"
    del "%TEMP%\_aadep.txt" >nul 2>nul

    if not "%MISSING%"=="" (
        echo.
        echo [X] 依赖仍然缺失: %MISSING%
        echo     原因通常是当前机器无网络。两种解决办法：
        echo       方案A（离线包）: 在有网机器执行
        echo           pip download -r requirements.txt -d pkgs
        echo         把 pkgs 目录拷到本机后执行
        echo           %PY% -m pip install --no-index --find-links=pkgs -r requirements.txt
        echo       方案B（只验证核心逻辑，无需完整依赖）:
        echo           %PY% verify.py
        echo.
        echo     是否仍要继续启动服务? 通常缺少 fastapi 会启动失败。
        choice /c YN /m "继续启动服务 [Y/N]"
        if errorlevel 2 goto :end
    ) else (
        echo [√] 依赖安装完成
    )
) else (
    echo [√] 核心依赖齐全，跳过安装
)
echo.

REM ---------- 4. 数据目录 ----------
if not exist "data\vector_db" mkdir "data\vector_db"
if not exist "data\memory"    mkdir "data\memory"
if not exist "data\uploads"   mkdir "data\uploads"

echo ========================================
echo  🚀 启动服务（Mock 模式，无需 Key）
echo     API 文档 : http://localhost:8000/docs
echo     健康检查 : http://localhost:8000/health
echo     监控指标 : http://localhost:8000/metrics
echo ========================================
echo.

REM ---------- 5. 初始化演示数据 ----------
%PY% init_data.py 2>nul

REM ---------- 6. 启动 ----------
%PY% main.py

:end
echo.
echo 服务已退出。
pause
