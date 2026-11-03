#!/bin/bash
# ============================================================
# AI智能体平台 一键启动脚本
# 设计原则：环境已有依赖则直接启动，绝不因联网失败而中断
# ============================================================

cd "$(dirname "$0")" || exit 1

# ---- 选择Python解释器 ----
PY=python3
if [ -d venv ]; then
    # 优先用已有虚拟环境（如果里面有langchain）
    if venv/bin/python -c "import langchain" 2>/dev/null; then
        PY=venv/bin/python
    fi
fi

echo "========================================"
echo " AI智能体平台 一键启动"
echo "========================================"
echo "🐍 Python: $($PY --version 2>&1)"
echo ""

# ---- 检查 .env ----
if [ ! -f .env ]; then
    echo "📋 复制 .env.example → .env (默认Mock模式，无需API Key)"
    cp .env.example .env
fi

# ---- 依赖检查：已装则跳过，缺包才尝试安装 ----
echo "🔍 检查核心依赖..."
MISSING=$($PY - <<'EOF'
import importlib.util
mods = ["langchain_core", "langchain", "langgraph", "fastapi", "uvicorn",
        "pydantic", "pydantic_settings", "slowapi", "prometheus_client",
        "structlog", "tenacity", "sse_starlette", "chromadb"]
miss = [m for m in mods if importlib.util.find_spec(m) is None]
print(" ".join(miss))
EOF
)

if [ -n "$MISSING" ]; then
    echo "⚠️  缺少依赖: $MISSING"
    echo "📦 尝试安装（若当前环境无网络，请在有网机器上预装）..."
    $PY -m pip install -q -r requirements-lite.txt \
        -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null \
        || $PY -m pip install -q -r requirements-lite.txt 2>/dev/null \
        || echo "❌ 依赖安装失败（可能无网络）。Mock模式核心验证可运行: python3 verify.py"
else
    echo "✅ 核心依赖齐全，跳过安装"
fi

# ---- 数据目录 ----
mkdir -p data/vector_db data/memory data/uploads

echo ""
echo "========================================"
echo " 🚀 启动服务（Mock模式，无需Key）"
echo "    API文档：http://localhost:8000/docs"
echo "    健康检查：http://localhost:8000/health"
echo "    监控指标：http://localhost:8000/metrics"
echo "========================================"
echo ""

# ---- 初始化演示数据 ----
$PY init_data.py 2>/dev/null || true

# ---- 启动 ----
exec $PY main.py
