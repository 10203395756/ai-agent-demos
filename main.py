"""
生产级FastAPI服务层
工程化能力覆盖：
- 限流保护（SlowApi按IP限流）
- 全局异常处理与统一错误响应
- CORS跨域配置
- SSE流式输出
- 请求链路追踪（TraceID）
- Prometheus监控指标端点
- 健康检查
- 请求/响应日志
- API版本化
- 三个Demo的完整REST接口
"""
from __future__ import annotations
import asyncio
import time
import uuid
import json
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Depends

# python-multipart 是“文件上传”接口的专属依赖（可选）。
# 缺失时不应导致整个应用无法启动：这里做可用性检测，缺包时上传接口自动降级为友好提示。
import importlib.util as _importlib_util
try:
    _MULTIPART_AVAILABLE = _importlib_util.find_spec("multipart") is not None
except Exception:  # pragma: no cover - 极端导入环境下保守降级
    _MULTIPART_AVAILABLE = False
try:
    from fastapi import UploadFile, File, Form
except Exception:  # pragma: no cover
    UploadFile = File = Form = None  # type: ignore
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool

import sys
sys.path.insert(0, str(Path(__file__).parent))
from common.config import get_settings
from common.logger import setup_logging, get_logger
from common.metrics import MetricsMiddleware, metrics_endpoint, ACTIVE_SESSIONS

setup_logging()
logger = get_logger("service")

# ============ 全局实例 ============
limiter = Limiter(key_func=get_remote_address)

# 三个Demo系统（延迟初始化，避免启动时加载模型）
_rag_system = None
_tool_agent = None
_multi_agent = None


def get_rag():
    global _rag_system
    if _rag_system is None:
        from demo1_rag_memory.rag_memory import RAGChain
        _rag_system = RAGChain()
    return _rag_system


def get_tool_agent():
    global _tool_agent
    if _tool_agent is None:
        from demo2_tools_agent.tools_agent import ToolAgent, registry
        _tool_agent = ToolAgent()
    return _tool_agent


def get_multi_agent():
    global _multi_agent
    if _multi_agent is None:
        from demo3_langgraph_multi_agent.multi_agent import MultiAgentPlatform
        _multi_agent = MultiAgentPlatform()
    return _multi_agent


# 内置状态图（与 demo3 中 build_multi_agent_graph() 的结构保持一致）
# 作用：无论本机 langgraph 版本/依赖是否完整，状态图接口都能“秒回”，
#       不会因为动态导出（draw_mermaid）卡住或失败而影响面试演示。
STATIC_MERMAID = """graph TD
    start_node(["START"]) --> planner{"Planner<br/>任务规划<br/>判断类型 + 拆解步骤"}
    planner -->|research 研究类| research_agent["ResearchAgent<br/>信息检索与整理"]
    planner -->|coding 编码类| coding_agent["CodingAgent<br/>代码 / 技术方案"]
    planner -->|analysis 分析类| analysis_agent["AnalysisAgent<br/>推理与评估"]
    planner -->|general 普通问答| synthesizer
    research_agent -->|needs_review = true| human_review{"HumanReview<br/>人工审核<br/>Human-in-the-loop"}
    research_agent -->|false| synthesizer
    coding_agent -->|needs_review = true| human_review
    coding_agent -->|false| synthesizer
    analysis_agent -->|needs_review = true| human_review
    analysis_agent -->|false| synthesizer
    human_review -->|通过 / 确认| synthesizer["Synthesizer<br/>多 Agent 结果汇总"]
    human_review -->|打回重做| research_agent
    human_review -->|打回重做| coding_agent
    human_review -->|打回重做| analysis_agent
    synthesizer --> end_node(["END"])
"""


async def _run_blocking(func, timeout: float = 15.0):
    """把同步阻塞调用丢到线程池并加超时，避免阻塞事件循环导致请求“一直 loading”。

    LangGraph 的 invoke / get_state / draw_mermaid 都是同步阻塞实现，
    若直接在 async 路由里调用，会占满事件循环，表现为接口长时间转圈甚至拖垮整个服务。
    """
    return await asyncio.wait_for(run_in_threadpool(func), timeout=timeout)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI智能体服务启动", mode=get_settings().RUN_MODE)
    yield
    logger.info("AI智能体服务关闭")


app = FastAPI(
    title="AI智能体平台",
    description="LangChain/LangGraph + RAG + 多工具 + 多智能体协作，企业级生产级架构",
    version="1.0.0",
    lifespan=lifespan,
)

# ============ 中间件 ============
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if get_settings().ENABLE_METRICS:
    app.add_middleware(MetricsMiddleware)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """给每个请求分配trace_id，注入响应头"""
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4())[:8])
    request.state.trace_id = trace_id
    start = time.time()
    response = await call_next(request)
    cost = time.time() - start
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Response-Time"] = f"{cost:.3f}s"
    logger.info("HTTP请求", trace=trace_id, method=request.method, path=request.url.path,
                status=response.status_code, cost=round(cost, 3))
    return response


# ============ 统一异常处理 ============
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未捕获异常", trace=request.state.trace_id, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {str(exc)[:100]}",
            "trace_id": getattr(request.state, "trace_id", ""),
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "参数校验失败", "details": exc.errors(),
                 "trace_id": getattr(request.state, "trace_id", "")}
    )


# ============ 请求数据模型 ============
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000, description="用户问题")
    session_id: Optional[str] = Field(None, description="会话ID，不传则新建")
    user_id: str = Field("default", description="用户ID，用于长期记忆")
    stream: bool = Field(False, description="是否流式输出")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    user_id: str = "default"


class HumanFeedbackRequest(BaseModel):
    thread_id: str = Field(..., description="多Agent任务线程ID")
    feedback: str = Field(..., description="人工反馈：通过 / 具体修改意见")


class DocumentIngestRequest(BaseModel):
    text: str = Field(..., description="要入库的文本内容")
    source: str = Field("api_input", description="来源标识")


# ============ 健康检查 & 监控 ============
@app.get("/health", tags=["系统"])
async def health_check():
    return {
        "status": "ok",
        "mode": get_settings().RUN_MODE,
        "timestamp": time.time(),
        "services": {
            "rag": _rag_system is not None,
            "tool_agent": _tool_agent is not None,
            "multi_agent": _multi_agent is not None,
        }
    }


@app.get("/metrics", tags=["系统"], include_in_schema=False)
async def metrics():
    return metrics_endpoint()


@app.get("/", tags=["系统"])
async def root():
    return {
        "service": "AI智能体平台 Demo",
        "version": "1.0.0",
        "mode": get_settings().RUN_MODE,
        "docs": "/docs",
        "demos": [
            {"name": "Demo1 RAG+长期记忆", "endpoints": ["/api/v1/rag/query", "/api/v1/rag/ingest"]},
            {"name": "Demo2 多工具智能体", "endpoints": ["/api/v1/agent/chat", "/api/v1/agent/tools"]},
            {"name": "Demo3 多智能体协作", "endpoints": ["/api/v1/multi-agent/submit", "/api/v1/multi-agent/feedback"]},
        ]
    }


# ============ Demo1：RAG知识库接口 ============
@app.post("/api/v1/rag/query", tags=["Demo1 RAG知识库"])
@limiter.limit(f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute")
async def rag_query(request: Request, body: QueryRequest):
    """RAG知识库问答，支持会话上下文和长期记忆"""
    rag = get_rag()
    if body.stream:
        async def generate():
            async for chunk in rag.query(body.question, body.session_id, body.user_id, stream=True):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        result = rag.query(body.question, body.session_id, body.user_id, stream=False)
        return {"code": 0, "data": result}


@app.post("/api/v1/rag/ingest", tags=["Demo1 RAG知识库"])
@limiter.limit("30/minute")
async def rag_ingest(request: Request, body: DocumentIngestRequest):
    """文本入库到知识库"""
    rag = get_rag()
    chunks = rag.ingest_text(body.text, body.source)
    return {"code": 0, "data": {"chunks_added": chunks, "message": f"成功入库{chunks}个切片"}}


if _MULTIPART_AVAILABLE:
    @app.post("/api/v1/rag/upload", tags=["Demo1 RAG知识库"])
    @limiter.limit("10/minute")
    async def rag_upload(request: Request, file: UploadFile = File(...)):
        """上传文件入库（支持txt/md/pdf/docx）"""
        save_path = Path(f"./data/uploads/{file.filename}")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(await file.read())
        rag = get_rag()
        chunks = rag.ingest_file(str(save_path))
        return {"code": 0, "data": {"filename": file.filename, "chunks_added": chunks}}
else:
    logger.warning(
        "未检测到 python-multipart，文件上传接口已降级。"
        "需要该功能请执行：pip install python-multipart"
    )

    @app.post("/api/v1/rag/upload", tags=["Demo1 RAG知识库（需安装 python-multipart）"])
    async def rag_upload_unavailable(request: Request):
        """文件上传依赖 python-multipart，未安装时返回明确的修复指引（不再导致服务启动失败）"""
        raise HTTPException(
            status_code=503,
            detail=(
                "文件上传功能需要安装 python-multipart：pip install python-multipart。"
                "也可改用 /api/v1/rag/ingest 直接提交文本内容。"
            ),
        )


@app.get("/api/v1/rag/sessions/{session_id}/memory", tags=["Demo1 RAG知识库"])
async def rag_user_memory(session_id: str, user_id: str = "default"):
    """查看用户长期记忆"""
    rag = get_rag()
    profile = rag.memory.get_profile(user_id)
    return {"code": 0, "data": {"user_id": user_id, "facts": profile.facts, "preferences": profile.preferences}}


# ============ Demo2：工具智能体接口 ============
@app.post("/api/v1/agent/chat", tags=["Demo2 工具智能体"])
@limiter.limit(f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute")
async def agent_chat(request: Request, body: ChatRequest):
    """多工具调用智能体对话，自动选择工具、支持多轮上下文"""
    agent = get_tool_agent()
    result = agent.run(body.message, body.session_id)
    return {"code": 0, "data": result}


@app.post("/api/v1/agent/chat/stream", tags=["Demo2 工具智能体"])
@limiter.limit(f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute")
async def agent_chat_stream(request: Request, body: ChatRequest):
    """工具智能体流式对话（SSE，包含工具调用事件）"""
    agent = get_tool_agent()

    async def generate():
        async for event in agent.stream(body.message, body.session_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/v1/agent/tools", tags=["Demo2 工具智能体"])
async def agent_list_tools():
    """查看已注册的所有工具（工具发现机制）"""
    from demo2_tools_agent.tools_agent import registry
    return {"code": 0, "data": {"tools": registry.list_tools(), "count": len(registry.list_tools())}}


# ============ Demo3：多智能体协作接口 ============
@app.post("/api/v1/multi-agent/submit", tags=["Demo3 多智能体协作"])
@limiter.limit(f"{get_settings().RATE_LIMIT_PER_MINUTE}/minute")
async def multi_agent_submit(request: Request, body: ChatRequest):
    """提交任务到多智能体平台，自动规划-路由-执行-审核"""
    ACTIVE_SESSIONS.inc()
    try:
        platform = get_multi_agent()
        # 同步阻塞调用放入线程池，避免阻塞事件循环
        result = await _run_blocking(
            lambda: platform.submit_task(body.message, body.session_id, body.user_id),
            timeout=120.0,
        )
        return {"code": 0, "data": result}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="多智能体任务执行超时（>120s），请稍后重试或简化任务")
    finally:
        ACTIVE_SESSIONS.dec()


@app.post("/api/v1/multi-agent/feedback", tags=["Demo3 多智能体协作"])
async def multi_agent_feedback(request: Request, body: HumanFeedbackRequest):
    """提交人工反馈，继续被中断的任务（Human-in-the-loop）"""
    platform = get_multi_agent()
    result = await _run_blocking(
        lambda: platform.submit_human_feedback(body.thread_id, body.feedback),
        timeout=120.0,
    )
    return {"code": 0, "data": result}


@app.get("/api/v1/multi-agent/status/{thread_id}", tags=["Demo3 多智能体协作"])
async def multi_agent_status(thread_id: str):
    """查询任务执行状态"""
    platform = get_multi_agent()
    status = await _run_blocking(
        lambda: platform.get_execution_status(thread_id),
        timeout=30.0,
    )
    return {"code": 0, "data": status}


@app.get("/api/v1/multi-agent/graph", tags=["Demo3 多智能体协作"])
async def multi_agent_graph(source: str = "static", timeout: float = 8.0):
    """导出LangGraph图结构（Mermaid可视化）

    - source=static（默认）：返回内置状态图，稳定秒回，适合面试演示
    - source=live：尝试用本机 LangGraph 的 draw_mermaid() 实时导出，带超时与降级保护
    """
    if source == "live":
        def _export():
            platform = get_multi_agent()
            return platform.app.get_graph().draw_mermaid()

        try:
            mermaid = await _run_blocking(_export, timeout=timeout)
            return {"code": 0, "data": {"mermaid": mermaid, "source": "langgraph"}}
        except asyncio.TimeoutError:
            return {"code": 0, "data": {
                "mermaid": STATIC_MERMAID,
                "source": "static_fallback",
                "note": f"实时导出超过 {timeout}s 未返回，已回退内置状态图",
            }}
        except Exception as e:
            return {"code": 0, "data": {
                "mermaid": STATIC_MERMAID,
                "source": "static_fallback",
                "note": f"实时导出失败（{type(e).__name__}: {str(e)[:160]}），已回退内置状态图",
            }}

    return {"code": 0, "data": {"mermaid": STATIC_MERMAID, "source": "static"}}


# ============ 启动入口 ============
if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
