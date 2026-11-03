"""
LLM客户端工厂：根据RUN_MODE自动切换Mock或真实大模型，对上层完全透明
"""
from __future__ import annotations
import time
import re
import hashlib
from typing import List, Optional, Any, AsyncIterator
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, AIMessageChunk
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
import asyncio

from .config import get_settings


# ============== Mock LLM：离线也能完整演示Agent流程 ==============
class MockChatModel(BaseChatModel):
    """离线模拟大模型：根据prompt特征返回结构化结果，支持Function Calling和流式"""

    model_name: str = "mock-llm"

    @property
    def _llm_type(self) -> str:
        return "mock-chat"

    def _generate(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        # 检测是否需要调用工具（Function Calling）
        tools = kwargs.get("tools", [])
        last_user_msg = ""
        for m in reversed(messages):
            if m.type == "human":
                last_user_msg = m.content
                break

        # 关键：如果已经存在工具执行结果（ToolMessage），说明工具调用已完成，
        # 此时应基于工具结果生成最终答案，而不是再次调用工具（避免死循环）。
        tool_results = [m for m in messages if m.type == "tool"]
        if tool_results:
            observations = "\n".join(m.content for m in tool_results)
            answer = (
                f"【智能体回答】根据工具执行结果：\n\n{observations[:600]}\n\n"
                f"针对您的问题「{last_user_msg}」，以上信息由智能体自动调用工具获取。"
                f"（Mock模式演示：真实模式下由大模型基于工具返回结果组织自然语言回答）"
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])

        # 简单规则：识别工具调用意图（可能同时命中多个工具，模拟串行多工具调用）
        tool_calls_spec = self._maybe_call_tools(last_user_msg, tools)
        if tool_calls_spec:
            tool_calls = []
            for i, tc in enumerate(tool_calls_spec):
                tool_calls.append({
                    "id": f"call_{hashlib.md5((last_user_msg+str(i)).encode()).hexdigest()[:8]}",
                    "name": tc["name"],
                    "args": tc["args"],
                })
            ai_msg = AIMessage(content="", tool_calls=tool_calls)
        else:
            # 普通问答，基于RAG上下文拼接答案
            ctx = self._extract_context(messages)
            answer = self._mock_answer(last_user_msg, ctx)
            ai_msg = AIMessage(content=answer)

        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs) -> AsyncIterator[ChatGenerationChunk]:
        """流式输出模拟"""
        result = self._generate(messages, stop, run_manager, **kwargs)
        content = result.generations[0].message.content
        if result.generations[0].message.tool_calls:
            # 工具调用直接返回
            yield ChatGenerationChunk(message=result.generations[0].message)
            return
        # 逐字流式，模拟真实SSE
        for ch in content:
            await asyncio.sleep(0.01)
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))

    def _maybe_call_tools(self, user_msg: str, tools: List[dict]) -> List[dict]:
        """根据关键词判断需要调用哪些工具，模拟Function Calling决策。

        返回列表：可同时命中多个工具，用于演示"一次规划、串行多工具调用"。
        """
        if not tools:
            return []
        msg_lower = user_msg.lower()
        tool_names = {t.get("function", {}).get("name", t.get("name")): t for t in tools}
        planned: List[dict] = []

        # 1) 天气意图
        if any(k in msg_lower for k in ["天气", "气温", "下雨", "温度"]) and "get_weather" in tool_names:
            city = "北京"
            for c in ["北京", "上海", "广州", "深圳", "贵阳", "杭州", "成都"]:
                if c in msg_lower:
                    city = c
            planned.append({"name": "get_weather", "args": {"city": city}})

        # 2) 时间意图
        if any(k in msg_lower for k in ["几点", "什么时间", "当前时间", "现在时间"]) and "get_current_time" in tool_names:
            planned.append({"name": "get_current_time", "args": {}})

        # 3) 数据库查询意图
        if any(k in msg_lower for k in ["查订单", "订单号", "用户信息", "查数据库", "订单记录"]) and "query_db" in tool_names:
            planned.append({"name": "query_db", "args": {"sql": "SELECT * FROM orders LIMIT 5"}})

        # 4) 计算器意图
        if (any(k in msg_lower for k in ["计算", "等于多少", "折算", "打折", "多少钱", "乘以", "除以", "算一下"])
                or re.search(r"\d+\s*[\+\-\*/]\s*\d+", msg_lower)) and "calculator" in tool_names:
            expr = self._extract_expression(user_msg)
            planned.append({"name": "calculator", "args": {"expression": expr or "0"}})

        # 5) 网页搜索意图（兜底；若已有其他具体意图，则搜索作为补充也一起调用）
        if any(k in msg_lower for k in ["搜索", "搜一下", "最新动态", "最新进展", "新闻", "search"]) and "web_search" in tool_names:
            q = msg_lower
            for w in ["搜索", "搜一下", "顺便", "一下", "最新动态", "最新进展"]:
                q = q.replace(w, "")
            planned.append({"name": "web_search", "args": {"query": q.strip() or user_msg}})

        return planned

    @staticmethod
    def _extract_expression(text: str) -> str:
        """从自然语言里抽取可计算的表达式（供Mock演示，真实模式由LLM完成）"""
        import re as _re
        # 直接含运算符的表达式
        m = _re.search(r"[\d\.]+(?:\s*[\+\-\*/]\s*[\d\.]+)+", text)
        if m:
            return m.group().replace(" ", "")
        # "打X折" / "减Y" 这类中文描述
        nums = _re.findall(r"[\d\.]+", text)
        if "折" in text and len(nums) >= 2:
            base = float(nums[0])
            pct = nums[1]
            # "85折" 按 ×0.85 计算；"8.5折" 同样 ×0.85
            rate = f"0.{pct}" if "." not in pct else str(float(pct) / 10)
            expr = f"{base}*{rate}"
            if len(nums) >= 3:
                expr += f"-{nums[2]}"
            return expr
        if len(nums) >= 2 and any(k in text for k in ["乘", "加", "减", "除以"]):
            return f"{nums[0]}+{nums[1]}"
        return ""

    def _extract_context(self, messages) -> str:
        """从 system prompt 中精确提取【检索到的上下文】片段

        prompt 中该标记可能出现两次（说明性文字 + 真实数据位置），
        因此从后往前找最后一个标记，才是真正注入的上下文。
        """
        for m in messages:
            if m.type == "system" and "检索到的上下文" in m.content:
                content = m.content
                marker = "【检索到的上下文】"
                idx = content.rfind(marker)
                if idx == -1:
                    return ""
                ctx = content[idx + len(marker):].strip()
                if ctx.startswith("（知识库中无相关内容"):
                    return ""
                return ctx
        return ""

    def _mock_answer(self, question: str, context: str) -> str:
        if context:
            return (
                f"【基于知识库回答】我检索到以下相关资料：\n\n"
                f"{context[:400]}\n\n"
                f"针对您的问题「{question}」，以上是知识库中召回的相关内容，"
                f"由RAG链路经『向量+关键词混合检索 → 相关度排序 → 上下文压缩』生成。"
            )
        return (
            f"【智能体回答】您的问题是：{question}\n\n"
            f"这是由AI智能体系统生成的模拟回答。在真实模式下，将调用大模型API结合工具执行结果给出完整答案。\n"
            f"本次回答由Mock模式生成，用于演示完整的Agent调用链路、工具编排和流式输出。"
        )

    def bind_tools(self, tools):
        return self.bind(tools=[_tool_to_dict(t) for t in tools])


def _tool_to_dict(tool) -> dict:
    if hasattr(tool, "name") and hasattr(tool, "args_schema"):
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": getattr(tool, "description", ""),
                "parameters": tool.args_schema.model_json_schema() if hasattr(tool.args_schema, "model_json_schema") else {}
            }
        }
    return tool


def get_llm(temperature: float = 0.3, streaming: bool = False) -> BaseChatModel:
    """工厂方法：统一获取LLM实例，Mock/Real透明切换"""
    settings = get_settings()
    if settings.RUN_MODE == "mock":
        return MockChatModel()

    # 真实模式
    provider = settings.LLM_PROVIDER
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            temperature=temperature,
            streaming=streaming,
        )
    elif provider == "qianfan":
        from langchain_qianfan import QianfanChatEndpoint
        return QianfanChatEndpoint(
            model=settings.QIANFAN_MODEL,
            qianfan_ak=settings.QIANFAN_AK,
            qianfan_sk=settings.QIANFAN_SK,
            temperature=temperature,
            streaming=streaming,
        )
    elif provider == "dashscope":
        from langchain_dashscope import ChatDashScope
        return ChatDashScope(
            model=settings.DASHSCOPE_MODEL,
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
            temperature=temperature,
            streaming=streaming,
        )
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
            temperature=temperature,
            streaming=streaming,
        )
    else:
        raise ValueError(f"不支持的LLM提供者: {provider}")


def get_embeddings():
    """获取Embedding模型，Mock/Real切换

    mock 模式：使用内置的离线确定性 Embedding，无需联网下载模型，
               基于字符 n-gram 哈希生成向量，语义相近文本相似度更高。
    real 模式：使用 HuggingFace 本地模型或云端 Embedding。
    """
    settings = get_settings()
    if settings.RUN_MODE == "mock":
        return _OfflineHashEmbeddings(size=384)
    if settings.EMBEDDING_PROVIDER == "local":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
        except Exception:
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings
                return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
            except Exception:
                return _OfflineHashEmbeddings(size=384)
    from langchain_community.embeddings import FakeEmbeddings
    return FakeEmbeddings(size=384)


# ============== 离线确定性 Embedding（无需下载模型） ==============
from langchain_core.embeddings import Embeddings as _BaseEmbeddings


class _OfflineHashEmbeddings(_BaseEmbeddings):
    """离线哈希 Embedding：把文本映射为固定维度向量，无需联网。

    原理：对文本的字符 2-gram / 3-gram 做哈希，累加到向量桶中并归一化。
    这样语义/字面相近的文本会得到更相似的向量，足以演示 RAG 检索链路。
    """

    def __init__(self, size: int = 384):
        self.size = size

    def _vec(self, text: str) -> list[float]:
        import hashlib
        import math
        vec = [0.0] * self.size
        text = (text or "").strip().lower()
        if not text:
            return vec
        grams = []
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                grams.append(text[i:i + n])
        if not grams:
            grams = [text]
        for g in grams:
            h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
            idx = h % self.size
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)
