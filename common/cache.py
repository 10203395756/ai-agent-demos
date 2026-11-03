"""
提示词缓存 + 会话缓存：减少重复LLM调用，降低成本
默认支持内存缓存，Redis可用时自动切换到Redis分布式缓存
"""
import hashlib
import json
import time
from typing import Optional, Any
from functools import wraps
from .config import get_settings
from .logger import get_logger
from .metrics import CACHE_HITS, CACHE_MISSES

logger = get_logger("cache")


class MemoryCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            value, expire_at = self._store[key]
            if expire_at > time.time():
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl: int):
        self._store[key] = (value, time.time() + ttl)

    def clear(self):
        self._store.clear()


class RedisCache:
    def __init__(self, redis_url: str):
        import redis
        self.client = redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> Optional[Any]:
        val = self.client.get(key)
        return json.loads(val) if val else None

    def set(self, key: str, value: Any, ttl: int):
        self.client.setex(key, ttl, json.dumps(value, ensure_ascii=False))


def _build_cache():
    settings = get_settings()
    try:
        if settings.ENABLE_CACHE and settings.REDIS_URL:
            return RedisCache(settings.REDIS_URL)
    except Exception as e:
        logger.warning("Redis不可用，回退到内存缓存", error=str(e))
    return MemoryCache()


cache = _build_cache()


def cache_key(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return "agent:" + hashlib.md5(raw.encode("utf-8")).hexdigest()


def cached(ttl: Optional[int] = None):
    """通用缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            settings = get_settings()
            actual_ttl = ttl or settings.CACHE_TTL_SECONDS
            if not settings.ENABLE_CACHE:
                return func(*args, **kwargs)
            key = cache_key(func.__name__, json.dumps(args, default=str), json.dumps(kwargs, default=str, sort_keys=True))
            val = cache.get(key)
            if val is not None:
                CACHE_HITS.inc()
                logger.info("缓存命中", func=func.__name__)
                return val
            CACHE_MISSES.inc()
            result = func(*args, **kwargs)
            cache.set(key, result, actual_ttl)
            return result
        return wrapper
    return decorator
