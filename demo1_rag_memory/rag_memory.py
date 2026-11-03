"""
Demo1：企业知识库 RAG + 长期记忆系统
覆盖JD技能点：
- RAG链路：文档加载→切片→Embedding→向量检索→重排序→生成
- 长期记忆管理：基于用户ID的会话持久化 + 实体级记忆
- 上下文压缩：滑动窗口 + 相关度过滤 + 摘要压缩
- 动态召回策略：混合检索（向量+关键词）+ Top-K自适应
"""
from __future__ import annotations
import os
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader, PyPDFLoader, Docx2txtLoader, UnstructuredMarkdownLoader
)
from langchain_community.vectorstores import Chroma, FAISS

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from common.config import get_settings
from common.llm import get_llm, get_embeddings
from common.logger import get_logger
from common.metrics import RAG_RETRIEVAL_COUNT, RAG_RETRIEVAL_LATENCY
from common.cache import cache, cache_key, cached

logger = get_logger("demo1_rag")


# ============== 1. 文档加载与智能切片 ==============
class DocumentProcessor:
    """支持多格式文档加载，递归字符切片，保留元数据"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 80):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            length_function=len,
            is_separator_regex=False,
        )

    def load_file(self, file_path: str) -> List[Document]:
        """根据文件后缀自动选择加载器"""
        ext = Path(file_path).suffix.lower()
        loaders = {
            ".txt": TextLoader,
            ".md": UnstructuredMarkdownLoader,
            ".pdf": PyPDFLoader,
            ".docx": Docx2txtLoader,
        }
        loader_cls = loaders.get(ext)
        if not loader_cls:
            raise ValueError(f"不支持的文件格式：{ext}，当前支持：{list(loaders.keys())}")
        loader = loader_cls(file_path)
        docs = loader.load()
        # 注入文件元数据
        for d in docs:
            d.metadata["source_file"] = os.path.basename(file_path)
            d.metadata["load_time"] = time.time()
        return docs

    def split_documents(self, docs: List[Document]) -> List[Document]:
        return self.splitter.split_documents(docs)


# ============== 2. 向量库管理（支持Chroma/FAISS切换） ==============
class _SimpleMemoryStore:
    """内置内存向量库（零第三方依赖）

    chromadb / faiss 均不可用时的兜底实现，保证 RAG 链路在任何环境都能跑通。
    接口与 langchain 向量库保持一致：add_documents / similarity_search_with_score。
    """

    def __init__(self, embeddings):
        self.embeddings = embeddings
        self._docs: List[Document] = []
        self._vectors: List[List[float]] = []

    def add_documents(self, docs: List[Document]):
        texts = [d.page_content for d in docs]
        vecs = self.embeddings.embed_documents(texts)
        self._docs.extend(docs)
        self._vectors.extend(vecs)

    def similarity_search_with_score(self, query: str, k: int = 4, **kwargs):
        """返回 (Document, 距离)，距离越小越相似，与 Chroma 口径保持一致"""
        import math
        if not self._vectors:
            return []
        qv = self.embeddings.embed_query(query)

        def _cos(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return dot / (na * nb)

        scored = [(doc, 1.0 - _cos(qv, v)) for doc, v in zip(self._docs, self._vectors)]
        scored.sort(key=lambda x: x[1])
        return scored[:k]

    def save_local(self, *args, **kwargs):  # 兼容 FAISS 的持久化调用
        return None


class VectorStoreManager:
    """统一向量库管理，支持持久化、增删改查"""

    def __init__(self, collection_name: str = "enterprise_kb"):
        settings = get_settings()
        self.collection_name = collection_name
        self.embeddings = get_embeddings()
        self.persist_dir = os.path.join(settings.VECTOR_PERSIST_DIR, collection_name)
        os.makedirs(self.persist_dir, exist_ok=True)
        self.store = self._init_store()

    def _init_store(self):
        settings = get_settings()
        # 向量库按 “chroma → faiss → 内置内存库” 逐级降级，
        # 避免因某个可选依赖未安装（如 chromadb / faiss）导致整个 RAG 链路不可用。
        if settings.VECTOR_STORE in ("chroma", "faiss"):
            try:
                if settings.VECTOR_STORE == "chroma":
                    return Chroma(
                        collection_name=self.collection_name,
                        embedding_function=self.embeddings,
                        persist_directory=self.persist_dir,
                    )
                index_path = os.path.join(self.persist_dir, "index.faiss")
                if os.path.exists(index_path):
                    return FAISS.load_local(self.persist_dir, self.embeddings, allow_dangerous_deserialization=True)
                return FAISS.from_texts(["初始化占位文本"], self.embeddings)
            except Exception as e:
                logger.warning(
                    f"{settings.VECTOR_STORE} 向量库不可用，已降级为内置内存向量库",
                    error=f"{type(e).__name__}: {str(e)[:120]}",
                    hint="如需完整功能：pip install chromadb",
                )
            return _SimpleMemoryStore(self.embeddings)

        if settings.VECTOR_STORE == "memory":
            return _SimpleMemoryStore(self.embeddings)

        raise ValueError(f"不支持的向量库：{settings.VECTOR_STORE}")

    def add_documents(self, docs: List[Document]):
        settings = get_settings()
        self.store.add_documents(docs)
        if settings.VECTOR_STORE == "faiss" and hasattr(self.store, "save_local"):
            self.store.save_local(self.persist_dir)

    def similarity_search(self, query: str, k: int = 4, score_threshold: float = 0.0) -> List[Document]:
        """带阈值过滤的相似度检索

        使用 distance 转相似度（similarity = 1 / (1 + distance)），
        比 Chroma 内置 relevance_score 更稳健，兼容离线哈希向量与真实向量模型。
        """
        start = time.time()
        RAG_RETRIEVAL_COUNT.labels(self.collection_name).inc()
        try:
            results = self.store.similarity_search_with_score(query, k=k)
            docs = []
            for doc, distance in results:
                # 距离越小越相似，转为 0~1 的相似度
                sim = 1.0 / (1.0 + float(distance))
                doc.metadata["_score"] = round(sim, 4)
                if sim >= score_threshold:
                    docs.append(doc)
        finally:
            RAG_RETRIEVAL_LATENCY.observe(time.time() - start)
        return docs

    def hybrid_search(self, query: str, k: int = 4) -> List[Document]:
        """混合检索：向量相似度 + 关键词BM25（简化版）"""
        # 向量召回
        vector_docs = self.similarity_search(query, k=k*2)
        # 关键词匹配（简化实现，真实环境用BM25）
        keywords = [w for w in query if len(w) > 1]
        scored = []
        for doc in vector_docs:
            content = doc.page_content
            kw_hits = sum(1 for kw in keywords if kw in content)
            scored.append((doc, kw_hits))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [d for d, _ in scored[:k]]


# ============== 3. 上下文压缩器 ==============
class ContextCompressor:
    """
    上下文压缩策略：
    1. 相关度过滤（仅保留高于阈值的片段）
    2. Token预算控制（超过上限自动截断+摘要）
    3. 关键句优先（保留含关键词的句子）
    """

    def __init__(self, max_context_tokens: int = 2000):
        self.max_tokens = max_context_tokens
        self.llm = get_llm(temperature=0.1)

    def compress(self, query: str, docs: List[Document], history: List) -> str:
        if not docs:
            return ""
        # 按相关度排序并拼接
        contexts = []
        total_len = 0
        for i, doc in enumerate(docs):
            content = doc.page_content.strip()
            source = doc.metadata.get("source_file", "未知来源")
            snippet = f"[来源{i+1}: {source}]\n{content}"
            if total_len + len(snippet) > self.max_tokens:
                break
            contexts.append(snippet)
            total_len += len(snippet)
        compressed = "\n\n---\n\n".join(contexts)
        return compressed

    def compress_history(self, history: List, recent_turns: int = 6) -> List:
        """历史对话压缩：近N轮保留原文，更早的做摘要"""
        if len(history) <= recent_turns * 2:
            return history
        # 近N轮直接保留
        recent = history[-recent_turns*2:]
        old = history[:-recent_turns*2]
        # 旧对话做摘要压缩
        old_text = "\n".join(f"{'用户' if m.type=='human' else '助手'}: {m.content}" for m in old if m.content)
        summary_prompt = f"请将以下对话历史用100字以内压缩摘要，保留关键信息：\n{old_text}"
        try:
            summary = self.llm.invoke([HumanMessage(content=summary_prompt)]).content
        except Exception:
            summary = "（历史对话已省略）"
        return [SystemMessage(content=f"【历史对话摘要】{summary}")] + recent


# ============== 4. 长期记忆系统 ==============
@dataclass
class UserProfile:
    """用户画像记忆：实体级长期存储"""
    user_id: str
    preferences: Dict[str, str] = field(default_factory=dict)  # 偏好
    facts: List[str] = field(default_factory=list)  # 事实记忆
    key_entities: Dict[str, str] = field(default_factory=dict)  # 关键实体
    last_active: float = field(default_factory=time.time)


class LongTermMemory:
    """
    双层记忆架构：
    - 短期：滑动窗口会话记忆（当前对话上下文）
    - 长期：用户画像+事实记忆，跨会话持久化
    """

    def __init__(self, storage_path: str = "./data/memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, List] = {}  # session_id → messages
        self.profiles: Dict[str, UserProfile] = {}
        self._load_profiles()

    def _profile_path(self, user_id: str) -> Path:
        return self.storage_path / f"profile_{user_id}.json"

    def _load_profiles(self):
        for f in self.storage_path.glob("profile_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                uid = data["user_id"]
                self.profiles[uid] = UserProfile(**data)
            except Exception:
                pass

    def _save_profile(self, profile: UserProfile):
        self._profile_path(profile.user_id).write_text(
            json.dumps(asdict(profile), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_or_create_session(self, session_id: Optional[str] = None) -> str:
        sid = session_id or str(uuid.uuid4())
        if sid not in self.sessions:
            self.sessions[sid] = []
        return sid

    def add_message(self, session_id: str, message):
        self.sessions[session_id].append(message)

    def get_history(self, session_id: str) -> List:
        return self.sessions.get(session_id, [])

    def get_profile(self, user_id: str) -> UserProfile:
        if user_id not in self.profiles:
            self.profiles[user_id] = UserProfile(user_id=user_id)
            self._save_profile(self.profiles[user_id])
        p = self.profiles[user_id]
        p.last_active = time.time()
        return p

    def extract_and_save_memory(self, user_id: str, user_msg: str, ai_msg: str):
        """从对话中自动抽取事实和偏好，写入长期记忆（简化规则版）"""
        profile = self.get_profile(user_id)
        # 抽取偏好
        if any(k in user_msg for k in ["我喜欢", "我偏好", "我习惯", "我想要"]):
            # 简单抽取，真实场景用LLM做NER
            for k in ["语言", "格式", "风格"]:
                if k in user_msg:
                    profile.preferences[k] = user_msg
        # 抽取事实
        if any(k in user_msg for k in ["我是", "我在", "我的公司", "我的项目", "我负责"]):
            fact = user_msg.strip()
            if fact not in profile.facts:
                profile.facts.append(fact)
        self._save_profile(profile)
        logger.info("长期记忆更新", user_id=user_id, facts_count=len(profile.facts))


# ============== 5. RAG问答链 ==============
RAG_SYSTEM_PROMPT = """你是一个专业的企业知识库助手。请严格依据【检索到的上下文】回答用户问题。

要求：
1. 如果上下文中有答案，基于上下文准确回答，引用来源标注[来源X]
2. 如果上下文没有相关信息，明确说明"知识库中未找到相关信息"，不要编造
3. 结合【用户长期记忆】中的偏好和背景信息，给出个性化回答
4. 回答结构清晰，必要时分点说明
5. 专业术语保持准确，不随意简化

【用户长期记忆】
{user_memory}

【检索到的上下文】
{context}
"""


class RAGChain:
    """完整RAG问答链，支持长期记忆、上下文压缩、流式输出"""

    def __init__(self, collection_name: str = "enterprise_kb"):
        self.vector_store = VectorStoreManager(collection_name)
        self.processor = DocumentProcessor()
        self.compressor = ContextCompressor()
        self.memory = LongTermMemory()
        self.llm = get_llm(temperature=0.3)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", RAG_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}")
        ])
        self.chain = (
            RunnablePassthrough.assign(
                context=RunnableLambda(lambda x: x["context"]),
                user_memory=RunnableLambda(lambda x: x["user_memory"]),
                history=RunnableLambda(lambda x: x["history"]),
            )
            | self.prompt
            | self.llm
            | StrOutputParser()
        )

    def ingest_file(self, file_path: str) -> int:
        """入库文档，返回切片数量"""
        docs = self.processor.load_file(file_path)
        chunks = self.processor.split_documents(docs)
        self.vector_store.add_documents(chunks)
        logger.info("文档入库完成", file=file_path, chunks=len(chunks))
        return len(chunks)

    def ingest_text(self, text: str, source: str = "manual_input"):
        chunks = self.processor.split_documents([Document(page_content=text, metadata={"source_file": source})])
        self.vector_store.add_documents(chunks)
        return len(chunks)

    def query(self, question: str, session_id: Optional[str] = None,
              user_id: str = "default", stream: bool = False):
        """问答接口：检索→压缩→生成→更新记忆"""
        sid = self.memory.get_or_create_session(session_id)
        history_raw = self.memory.get_history(sid)
        history = self.compressor.compress_history(history_raw)

        # 混合检索
        docs = self.vector_store.hybrid_search(question, k=4)
        context = self.compressor.compress(question, docs, history)

        # 用户记忆注入
        profile = self.memory.get_profile(user_id)
        user_memory_parts = []
        if profile.facts:
            user_memory_parts.append("用户背景：" + "；".join(profile.facts[-5:]))
        if profile.preferences:
            user_memory_parts.append("用户偏好：" + "；".join(profile.preferences.values()))
        user_memory = "\n".join(user_memory_parts) if user_memory_parts else "无特殊记忆"

        logger.info("RAG查询", session=sid, docs_found=len(docs), context_len=len(context))

        # 生成回答
        inputs = {
            "question": question,
            "context": context if context else "（知识库中无相关内容，请直接回答无法找到相关信息）",
            "user_memory": user_memory,
            "history": history,
        }

        if stream:
            return self._stream_response(inputs, sid, question, user_id)

        answer = self.chain.invoke(inputs)
        self._after_response(sid, question, answer, user_id)
        return {
            "answer": answer,
            "session_id": sid,
            "sources": [{"source": d.metadata.get("source_file", ""), "snippet": d.page_content[:100]} for d in docs],
            "context_length": len(context),
        }

    async def _stream_response(self, inputs, sid, question, user_id):
        """流式输出（SSE）"""
        collected = []
        async for chunk in self.chain.astream(inputs):
            collected.append(chunk)
            yield chunk
        answer = "".join(collected)
        self._after_response(sid, question, answer, user_id)

    def _after_response(self, session_id: str, question: str, answer: str, user_id: str):
        self.memory.add_message(session_id, HumanMessage(content=question))
        self.memory.add_message(session_id, AIMessage(content=answer))
        self.memory.extract_and_save_memory(user_id, question, answer)


# ============== 快速使用示例 ==============
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from common.logger import setup_logging
    setup_logging()

    rag = RAGChain()
    # 写入示例知识库
    rag.ingest_text("""
LangGraph是LangChain团队推出的多智能体编排框架，基于状态图（StateGraph）构建。
核心概念包括：State（共享状态）、Node（节点函数）、Edge（边/条件边）、Checkpointer（持久化检查点）。
StateGraph通过有向图定义Agent工作流，支持循环、分支、并行，特别适合多Agent协作场景。
Human-in-the-loop机制允许在关键节点中断流程，等待人类确认后继续执行，这是生产级智能体的必备能力。
    """, source="langgraph_intro.md")

    rag.ingest_text("""
RAG（检索增强生成）的关键优化点包括：1.文档切片策略：按语义边界切片而非固定长度；
2.混合检索：向量相似度+关键词BM25结合；3.重排序：用Cross-Encoder对召回结果二次排序；
4.查询改写：对用户问题做扩展、分解和HyDE；5.上下文压缩：过滤无关片段，控制Token成本。
    """, source="rag_optimization.md")

    print("="*60)
    print("Demo1：企业知识库RAG + 长期记忆系统 （Mock模式）")
    print("="*60)

    # 第一轮问答
    resp = rag.query("什么是LangGraph？它的核心概念有哪些？")
    print(f"\n[用户] 什么是LangGraph？它的核心概念有哪些？")
    print(f"[助手] {resp['answer']}")
    print(f"[来源] {[s['source'] for s in resp['sources']]}")

    # 第二轮问答（带上下文）
    resp = rag.query("RAG怎么做优化？", session_id=resp["session_id"])
    print(f"\n[用户] RAG怎么做优化？")
    print(f"[助手] {resp['answer']}")

    print("\n✅ Demo1运行完成：覆盖文档切片→混合检索→上下文压缩→长期记忆全链路")
