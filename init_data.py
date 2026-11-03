# 初始化示例数据：启动服务后自动写入一份演示知识库
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.config import get_settings
settings = get_settings()
print("📚 初始化演示知识库数据...")
try:
    from demo1_rag_memory.rag_memory import RAGChain
    rag = RAGChain()
    rag.ingest_text("""
LangGraph是LangChain团队推出的多智能体编排框架，基于状态图（StateGraph）构建。
核心概念包括：State（共享状态）、Node（节点函数）、Edge（边/条件边）、Checkpointer（持久化检查点）。
StateGraph通过有向图定义Agent工作流，支持循环、分支、并行，特别适合多Agent协作场景。
Human-in-the-loop机制允许在关键节点中断流程，等待人类确认后继续执行，这是生产级智能体的必备能力。
Checkpointer可以把每一步的State持久化下来，支持断点续跑、故障恢复、执行状态查询。
    """.strip(), source="langgraph_intro.md")

    rag.ingest_text("""
RAG（检索增强生成）的关键优化点：
1. 文档切片策略：按语义边界切片而非固定长度，常用RecursiveCharacterTextSplitter；
2. 混合检索：向量相似度+关键词BM25结合，提升召回率；
3. 重排序：用Cross-Encoder对召回结果二次排序，提升准确率；
4. 查询改写：对用户问题做扩展、分解和HyDE；
5. 上下文压缩：过滤无关片段，控制Token成本。
    """.strip(), source="rag_optimization.md")

    rag.ingest_text("""
多智能体系统最佳实践：
- 从简单双Agent（规划+执行）开始，不要一开始就上很多Agent；
- 必须设置max_iterations防止无限循环；
- 关键节点加入Human-in-the-loop人工审核兜底；
- 用Checkpointer持久化状态，支持断点续跑；
- 每个节点有明确的输入输出约定，State设计要清晰；
- 做好监控、缓存、限流，控制Token成本。
    """.strip(), source="multi_agent_best_practice.md")

    print("✅ 演示知识库初始化完成（3篇文档已入库）")
except Exception as e:
    print(f"⚠️  知识库初始化跳过（需要向量库依赖）：{e}")
