# -*- coding: utf-8 -*-
"""
环境诊断脚本（Windows / macOS / Linux 通用）
用法：  python doctor.py
作用： 一次性检查 Python 版本、依赖安装情况、项目文件完整性、数据目录、端口占用，
       并给出针对性的修复命令。无需任何第三方依赖即可运行。
"""
import sys
import os
import importlib.util
import platform
import socket

OK = "[√]"
BAD = "[X]"
WARN = "[!]"

problems = []


def line():
    print("-" * 52)


print("=" * 52)
print(" AI 智能体平台 - 环境诊断")
print("=" * 52)

# ---------- 1. Python ----------
line()
print("【1】Python 环境")
print(f"  版本   : {sys.version.split()[0]}")
print(f"  解释器 : {sys.executable}")
print(f"  平台   : {platform.system()} {platform.release()}")
if sys.version_info >= (3, 10):
    print(f"  {OK} 版本满足要求 (>=3.10)")
else:
    print(f"  {BAD} 版本过低，请升级到 3.10 及以上")
    problems.append("升级 Python 到 3.10+")

# Windows 上提醒命令名差异
if platform.system() == "Windows":
    print(f"  {WARN} Windows 上命令是 python / py，不要用 python3")

# ---------- 2. 依赖 ----------
line()
print("【2】依赖检查")
# 核心必需依赖
CORE = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("langchain", "langchain"),
    ("langchain_core", "langchain-core"),
    ("langgraph", "langgraph"),
    ("chromadb", "chromadb"),
]
# 工程化依赖（缺了服务仍可能起，但功能不全）
EXTRA = [
    ("multipart", "python-multipart"),
    ("slowapi", "slowapi"),
    ("prometheus_client", "prometheus-client"),
    ("structlog", "structlog"),
    ("sse_starlette", "sse-starlette"),
    ("tenacity", "tenacity"),
]

missing_core = []
for mod, pkg in CORE:
    if importlib.util.find_spec(mod) is None:
        print(f"  {BAD} 缺少核心依赖: {mod}")
        missing_core.append(pkg)
    else:
        print(f"  {OK} {mod}")

missing_extra = []
for mod, pkg in EXTRA:
    if importlib.util.find_spec(mod) is None:
        print(f"  {WARN} 缺少工程化依赖: {mod}")
        missing_extra.append(pkg)

if missing_core:
    problems.append("安装核心依赖: " + " ".join(missing_core))

# ---------- 3. 项目文件 ----------
line()
print("【3】项目文件完整性")
HERE = os.path.dirname(os.path.abspath(__file__))
required = [
    "main.py",
    "verify.py",
    "init_data.py",
    ".env.example",
    os.path.join("common", "llm.py"),
    os.path.join("common", "config.py"),
    os.path.join("demo1_rag_memory", "rag_memory.py"),
    os.path.join("demo2_tools_agent", "tools_agent.py"),
    os.path.join("demo3_langgraph_multi_agent", "multi_agent.py"),
]
file_missing = []
for f in required:
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        print(f"  {OK} {f}")
    else:
        print(f"  {BAD} 缺失文件: {f}")
        file_missing.append(f)
if file_missing:
    problems.append("项目文件缺失，请重新解压完整工程")

# ---------- 4. .env 与数据目录 ----------
line()
print("【4】配置与数据目录")
env_path = os.path.join(HERE, ".env")
if os.path.exists(env_path):
    print(f"  {OK} .env 已存在")
    try:
        with open(env_path, "r", encoding="utf-8") as fp:
            content = fp.read().lower()
        if "mock" in content:
            print(f"  {OK} 检测到 Mock 模式配置（无需 API Key 即可运行）")
    except Exception:
        pass
else:
    print(f"  {WARN} .env 不存在（启动脚本会自动从 .env.example 复制）")

for d in ("data/vector_db", "data/memory", "data/uploads"):
    p = os.path.join(HERE, *d.split("/"))
    if os.path.isdir(p):
        print(f"  {OK} {d}/")
    else:
        print(f"  {WARN} {d}/ 不存在（启动脚本会自动创建）")

# ---------- 5. 端口 ----------
line()
print("【5】端口占用 (8000)")
def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        r = s.connect_ex(("127.0.0.1", port))
        return r != 0
    finally:
        s.close()

if port_free(8000):
    print(f"  {OK} 8000 端口空闲")
else:
    print(f"  {WARN} 8000 端口已被占用（可能是旧服务在跑）")
    print("       Windows 查看: netstat -ano | findstr :8000")
    print("       Windows 关闭: taskkill /PID <进程号> /F")
    print("       其他端口启动: 修改 .env 里的 PORT 或运行 python main.py --port 8001")

# ---------- 结论 ----------
line()
print("【诊断结论】")
if not problems:
    print(f"  {OK} 环境检查通过，可以直接启动：")
    print("       Windows : start_windows.bat  (或 python main.py)")
    print("       macOS/Linux : bash start.sh")
else:
    print(f"  {BAD} 发现以下问题，请先处理：")
    for i, p in enumerate(problems, 1):
        print(f"       {i}. {p}")
    print()
    print("  常见修复命令（Windows 用 pip，不要用 pip3）：")
    if missing_core:
        print(f"       python -m pip install {' '.join(missing_core)}")
        print(f"       国内镜像加速： python -m pip install {' '.join(missing_core)} -i https://pypi.tuna.tsinghua.edu.cn/simple")
    print("       仅验证核心逻辑（无需完整依赖）： python verify.py")
line()
print("提示：如果本机完全没网络，可先用 python verify.py 验证 Mock 模式核心逻辑。")
