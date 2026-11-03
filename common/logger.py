"""
结构化日志 + 请求追踪：为每次请求生成trace_id，便于链路排查

说明：structlog 为“可选增强”，缺失时自动降级为标准库 logging，
      保证服务在任何环境下都能正常启动（不再因为少装一个包就起不来）。
"""
import logging
import sys
import uuid

try:
    import structlog
except Exception:  # pragma: no cover - 缺少 structlog 时降级，不影响服务启动
    structlog = None

from .config import get_settings


def setup_logging():
    settings = get_settings()
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=settings.LOG_LEVEL)

    if structlog is None:
        logging.getLogger("ai-agent").warning(
            "未安装 structlog，已降级为标准库日志（如需结构化JSON日志：pip install structlog）"
        )
        return

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class _StdlibLogger:
    """structlog 缺失时的最小兼容实现，保持 .bind()/.info(event, **kv) 的调用方式不变"""

    def __init__(self, name: str, ctx: dict | None = None):
        self._logger = logging.getLogger(name)
        self._ctx = ctx or {}

    def bind(self, **kwargs):
        return _StdlibLogger(self._logger.name, {**self._ctx, **kwargs})

    def _log(self, level: int, event: str, **kwargs):
        ctx = {**self._ctx, **kwargs}
        exc_info = ctx.pop("exc_info", False)
        extra = " ".join(f"{k}={v}" for k, v in ctx.items())
        self._logger.log(level, f"{event} {extra}".rstrip(), exc_info=exc_info)

    def debug(self, event, **kwargs):
        self._log(logging.DEBUG, event, **kwargs)

    def info(self, event, **kwargs):
        self._log(logging.INFO, event, **kwargs)

    def warning(self, event, **kwargs):
        self._log(logging.WARNING, event, **kwargs)

    def error(self, event, **kwargs):
        self._log(logging.ERROR, event, **kwargs)


def get_logger(name: str = "ai-agent"):
    if structlog is None:
        return _StdlibLogger(name).bind(trace_id=str(uuid.uuid4())[:8])
    return structlog.get_logger(name).bind(trace_id=str(uuid.uuid4())[:8])
