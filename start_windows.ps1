# ============================================================
#  AI 智能体平台 - Windows PowerShell 一键启动脚本
#  用法（在项目目录下打开 PowerShell）：
#     powershell -ExecutionPolicy Bypass -File .\start_windows.ps1
#  若提示脚本被禁用，就用上面这条带 Bypass 的命令。
# ============================================================

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "AI 智能体平台"

# 切到脚本所在目录
Set-Location -Path $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " AI 智能体平台 一键启动 (Windows PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 定位 Python ----------
$py = $null
foreach ($cand in @("python", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cand; break }
}
if (-not $py) {
    Write-Host "[X] 未检测到 Python，请安装 Python 3.10+ 并加入 PATH" -ForegroundColor Red
    Write-Host "    下载: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

$ver = & $py --version 2>&1
Write-Host "[√] 解释器: $py ($ver)" -ForegroundColor Green

$ok = & $py -c "import sys; print(1 if sys.version_info>=(3,10) else 0)" 2>$null
if ($ok.Trim() -ne "1") {
    Write-Host "[X] Python 版本过低，需要 3.10 及以上" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host ""

# ---------- 2. 准备 .env ----------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env" -Force
    Write-Host "[i] 已生成 .env（默认 Mock 模式，无需 API Key）" -ForegroundColor Yellow
}
Write-Host "[√] 配置文件 .env 就绪" -ForegroundColor Green
Write-Host ""

# ---------- 3. 检查核心依赖 ----------
function Get-MissingDeps {
    $code = @"
import importlib.util as u, sys
mods = ['langchain_core','langchain','langgraph','fastapi','uvicorn','pydantic','pydantic_settings','slowapi','prometheus_client','structlog','sse_starlette','chromadb','multipart']
miss = [m for m in mods if u.find_spec(m) is None]
print(' '.join(miss))
"@
    return (& $py -c $code 2>$null)
}

Write-Host "[..] 检查核心依赖..." -ForegroundColor Gray
$missing = Get-MissingDeps

if ($missing.Trim() -ne "") {
    Write-Host "[!] 缺少依赖: $missing" -ForegroundColor Yellow
    Write-Host "[..] 尝试从清华镜像安装..." -ForegroundColor Gray
    & $py -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[..] 镜像失败，改用默认源..." -ForegroundColor Gray
        & $py -m pip install -r requirements.txt --quiet
    }
    $missing = Get-MissingDeps
    if ($missing.Trim() -ne "") {
        Write-Host ""
        Write-Host "[X] 依赖仍缺失: $missing" -ForegroundColor Red
        Write-Host "    常见原因是本机无网络。解决办法：" -ForegroundColor Yellow
        Write-Host "      方案A（离线包）: 有网机器执行" -ForegroundColor Yellow
        Write-Host "        pip download -r requirements.txt -d pkgs" -ForegroundColor Gray
        Write-Host "      拷贝 pkgs 到本机后执行：" -ForegroundColor Yellow
        Write-Host "        $py -m pip install --no-index --find-links=pkgs -r requirements.txt" -ForegroundColor Gray
        Write-Host "      方案B（只验证核心逻辑）:" -ForegroundColor Yellow
        Write-Host "        $py verify.py" -ForegroundColor Gray
        Write-Host ""
        $ans = Read-Host "是否仍要继续启动服务? (y/N)"
        if ($ans -notmatch "^[Yy]") { exit 1 }
    } else {
        Write-Host "[√] 依赖安装完成" -ForegroundColor Green
    }
} else {
    Write-Host "[√] 核心依赖齐全，跳过安装" -ForegroundColor Green
}
Write-Host ""

# ---------- 4. 数据目录 ----------
foreach ($d in @("data\vector_db", "data\memory", "data\uploads")) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 🚀 启动服务（Mock 模式，无需 Key）" -ForegroundColor Cyan
Write-Host "    API 文档 : http://localhost:8000/docs" -ForegroundColor White
Write-Host "    健康检查 : http://localhost:8000/health" -ForegroundColor White
Write-Host "    监控指标 : http://localhost:8000/metrics" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 5. 初始化演示数据 ----------
& $py init_data.py 2>$null

# ---------- 6. 启动 ----------
& $py main.py

Write-Host ""
Read-Host "服务已退出，按回车关闭窗口"
