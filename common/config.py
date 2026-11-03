"""
统一配置加载：支持.env文件与环境变量，Mock/Real双模式切换
"""
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 运行模式
    RUN_MODE: Literal["mock", "real"] = "mock"

    # LLM
    LLM_PROVIDER: str = "qianfan"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    QIANFAN_AK: str = ""
    QIANFAN_SK: str = ""
    QIANFAN_MODEL: str = "ernie-4.0-turbo-8k"
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen-plus"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Embedding
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # 服务
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # 工程化
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_PER_MINUTE: int = 60
    ENABLE_METRICS: bool = True
    ENABLE_CACHE: bool = True
    CACHE_TTL_SECONDS: int = 3600

    # 向量库
    VECTOR_STORE: str = "chroma"
    VECTOR_PERSIST_DIR: str = "./data/vector_db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
