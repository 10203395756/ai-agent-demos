"""
监控指标 + Token成本统计：Prometheus指标埋点
"""
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 请求指标
REQUEST_COUNT = Counter("http_requests_total", "HTTP请求总数", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP请求耗时", ["endpoint"], buckets=[0.1, 0.3, 0.5, 1, 2, 5, 10])

# LLM指标
LLM_CALL_COUNT = Counter("llm_calls_total", "LLM调用次数", ["provider", "model"])
LLM_TOKEN_USAGE = Counter("llm_token_usage_total", "Token消耗总量", ["model", "type"])  # type=prompt/completion
LLM_LATENCY = Histogram("llm_call_duration_seconds", "LLM调用耗时", ["model"], buckets=[0.5, 1, 2, 5, 10, 30])

# Agent指标
AGENT_TOOL_CALLS = Counter("agent_tool_calls_total", "工具调用次数", ["tool_name", "status"])
RAG_RETRIEVAL_COUNT = Counter("rag_retrieval_total", "RAG检索次数", ["collection"])
RAG_RETRIEVAL_LATENCY = Histogram("rag_retrieval_duration_seconds", "RAG检索耗时", buckets=[0.05, 0.1, 0.3, 0.5, 1])

# 缓存指标
CACHE_HITS = Counter("cache_hits_total", "缓存命中次数")
CACHE_MISSES = Counter("cache_misses_total", "缓存未命中次数")

# 活跃会话
ACTIVE_SESSIONS = Gauge("active_sessions", "当前活跃会话数")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.url.path).observe(duration)
        return response


def metrics_endpoint():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
