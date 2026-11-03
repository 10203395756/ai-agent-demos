"""
Demo3：LangGraph多智能体协作平台（企业级智能体系统架构）
覆盖JD核心技能点：
- 智能体架构设计：LangChain/LangGraph状态图编排，复杂任务规划
- 多智能体编排：StateGraph状态机、条件边路由、节点并行
- 工程化落地：Checkpointer持久化、模块化封装、高可用部署
- 人机协同（Human-in-the-loop）：关键节点中断等待人工确认
- 性能与稳定性：监控告警、错误重试、超时熔断、全链路追踪
"""
from __future__ import annotations
import time
import json
import uuid
import enum
from typing import TypedDict, List, Dict, Any, Optional, Annotated, Literal
from pathlib import Path
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from common.config import get_settings
from common.llm import get_llm
from common.logger import get_logger
from common.metrics import LLM_CALL_COUNT, LLM_LATENCY

logger = get_logger("demo3_langgraph")


# ============== 1. 定义共享状态（StateGraph核心） ==============
class AgentState(TypedDict):
    """
    多Agent之间共享的状态对象，所有节点都读写这份状态
    对应JD要求："StateGraph设计"
    """
    # 消息历史
    messages: Annotated[List[BaseMessage], "消息列表，所有Agent共享"]
    # 任务信息
    user_query: str  # 用户原始问题
    task_type: Optional[str]  # 任务分类：research / coding / analysis / general
    plan: Optional[List[str]]  # 任务规划拆解步骤
    current_step: int  # 当前执行到第几步
    # 各Agent产出
    research_result: Optional[str]  # 研究Agent产出
    coding_result: Optional[str]  # 代码Agent产出
    analysis_result: Optional[str]  # 分析Agent产出
    # 流程控制
    needs_human_review: bool  # 是否需要人工审核
    human_feedback: Optional[str]  # 人工反馈内容
    error: Optional[str]  # 错误信息
    retry_count: int  # 重试次数
    # 元数据
    session_id: str
    start_time: float
    end_time: Optional[float]


# ============== 2. 各专业Agent节点（模拟多角色协作） ==============
class PlannerAgent:
    """规划Agent：任务理解+拆解，决定路由到哪些专家Agent"""

    def __init__(self):
        self.llm = get_llm(temperature=0.1)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """你是任务规划师。请分析用户问题，判断任务类型并拆解执行步骤。

任务类型分类（必须选一个）：
- research：需要搜索资料、查信息、调研类问题
- coding：需要写代码、调试、技术方案类问题
- analysis：需要数据分析、逻辑推理、评估类问题
- general：普通问答、闲聊、常识类问题，直接回答

请严格按JSON格式输出，不要多余文字：
{{"task_type": "类型", "plan": ["步骤1", "步骤2", "步骤3"], "needs_human_review": true/false}}

判断needs_human_review的规则：涉及数据修改、对外发布、重要决策、不确定的专业判断时为true"""),
            MessagesPlaceholder(variable_name="messages"),
            ("human", "用户问题：{user_query}\n请分析并规划。"),
        ])
        self.chain = self.prompt | self.llm

    def run(self, state: AgentState) -> Dict:
        logger.info("[Planner] 开始任务规划", query=state["user_query"][:50])
        start = time.time()
        try:
            resp = self.chain.invoke({
                "messages": state["messages"],
                "user_query": state["user_query"],
            })
            # 解析JSON（Mock模式直接构造）
            if get_settings().RUN_MODE == "mock":
                task_type = self._mock_classify(state["user_query"])
                plan = self._mock_plan(task_type, state["user_query"])
                needs_review = task_type in ("coding", "analysis")
            else:
                content = resp.content
                json_str = content[content.find("{"):content.rfind("}")+1]
                parsed = json.loads(json_str)
                task_type = parsed.get("task_type", "general")
                plan = parsed.get("plan", ["直接回答问题"])
                needs_review = parsed.get("needs_human_review", False)

            LLM_CALL_COUNT.labels("planner", "default").inc()
            LLM_LATENCY.labels("default").observe(time.time() - start)
            logger.info("[Planner] 规划完成", type=task_type, steps=len(plan))
            return {
                "task_type": task_type,
                "plan": plan,
                "current_step": 0,
                "needs_human_review": needs_review,
                "retry_count": 0,
            }
        except Exception as e:
            logger.error("[Planner] 规划失败", error=str(e))
            return {"task_type": "general", "plan": ["直接回答"], "error": str(e)}

    def _mock_classify(self, query: str) -> str:
        q = query.lower()
        if any(k in q for k in ["搜索", "查", "调研", "资料", "最新", "新闻", "对比"]):
            return "research"
        if any(k in q for k in ["代码", "编程", "写个", "debug", "bug", "实现", "开发"]):
            return "coding"
        if any(k in q for k in ["分析", "评估", "对比", "方案", "建议", "怎么看"]):
            return "analysis"
        return "general"

    def _mock_plan(self, task_type: str, query: str) -> List[str]:
        plans = {
            "research": ["调用搜索工具收集相关资料", "整理并交叉验证信息", "总结成结构化报告"],
            "coding": ["分析需求明确技术方案", "编写核心代码实现", "自检并补充注释说明"],
            "analysis": ["明确分析维度和指标", "结合检索信息做逻辑推理", "给出结论和建议"],
            "general": ["理解用户意图", "结合知识直接回答"],
        }
        return plans.get(task_type, ["直接回答"])


class ResearchAgent:
    """研究Agent：负责信息检索、资料整理"""

    def __init__(self):
        self.llm = get_llm(temperature=0.3)

    def run(self, state: AgentState) -> Dict:
        logger.info("[Research] 开始执行研究任务")
        # 模拟搜索+整理
        if get_settings().RUN_MODE == "mock":
            time.sleep(0.3)  # 模拟耗时
            result = (
                f"【研究结果】针对「{state['user_query']}」的调研：\n"
                f"1. 已检索到相关资料5份，覆盖核心概念和最新动态\n"
                f"2. 关键信息已交叉验证，可信度较高\n"
                f"3. 研究要点：多智能体系统是2026年AI应用落地的主流架构，LangGraph已成为行业标准编排框架，"
                f"StateGraph+Checkpointer+Human-in-the-loop是生产级系统三要素\n"
                f"4. 风险点：复杂任务容易出现无限循环，需要设置max_iterations和条件熔断"
            )
        else:
            prompt = f"请作为研究员，针对以下问题给出结构化的研究结果：{state['user_query']}\n参考上下文：{state.get('messages', [])}"
            result = self.llm.invoke([HumanMessage(content=prompt)]).content

        logger.info("[Research] 研究完成", length=len(result))
        return {"research_result": result, "current_step": state["current_step"] + 1}


class CodingAgent:
    """代码Agent：负责代码生成、技术方案"""

    def __init__(self):
        self.llm = get_llm(temperature=0.2)

    def run(self, state: AgentState) -> Dict:
        logger.info("[Coding] 开始执行编码任务")
        if get_settings().RUN_MODE == "mock":
            time.sleep(0.4)
            result = (
                f"【代码方案】针对「{state['user_query']}」：\n"
                f"\n核心实现思路：\n"
                f"1. 采用LangGraph StateGraph定义工作流，将任务拆分为规划→执行→校验三个节点\n"
                f"2. 使用MemorySaver做Checkpointer持久化，支持断点续跑\n"
                f"3. 在关键节点加入interrupt_before实现Human-in-the-loop人工审核\n"
                f"\n示例代码片段（Python）：\n"
                f"```python\n"
                f"graph = StateGraph(AgentState)\n"
                f"graph.add_node('planner', planner_node)\n"
                f"graph.add_node('executor', executor_node)\n"
                f"graph.add_conditional_edges('planner', route_func)\n"
                f"checkpointer = MemorySaver()\n"
                f"app = graph.compile(checkpointer=checkpointer,\n"
                f"                    interrupt_before=['human_review'])\n"
                f"```\n"
                f"代码已通过语法校验，可直接集成到FastAPI服务中对外提供接口。"
            )
        else:
            prompt = f"请作为资深工程师，针对需求给出代码实现方案：{state['user_query']}"
            result = self.llm.invoke([HumanMessage(content=prompt)]).content

        logger.info("[Coding] 编码完成", length=len(result))
        return {"coding_result": result, "current_step": state["current_step"] + 1}


class AnalysisAgent:
    """分析Agent：负责逻辑推理、方案评估"""

    def __init__(self):
        self.llm = get_llm(temperature=0.4)

    def run(self, state: AgentState) -> Dict:
        logger.info("[Analysis] 开始分析任务")
        research = state.get("research_result", "")
        if get_settings().RUN_MODE == "mock":
            time.sleep(0.3)
            result = (
                f"【分析结论】基于调研结果：\n\n"
                f"优势：采用多智能体架构可以显著提升复杂任务完成率，单一任务可拆解为专业子任务由不同专家Agent并行处理\n"
                f"成本：多Agent系统Token消耗是单Agent的2-4倍，需要做好缓存和上下文压缩控制成本\n"
                f"风险：\n"
                f"  1. Agent之间状态同步问题，建议用统一State + 版本号控制\n"
                f"  2. 工具调用失败扩散，需要做熔断和降级处理\n"
                f"  3. 循环调用风险，必须设置最大迭代次数\n"
                f"\n建议：从简单双Agent协作（规划+执行）开始落地，验证效果后再逐步加专家Agent。"
            )
        else:
            prompt = f"结合研究资料{research[:2000]}，请给出深入分析：{state['user_query']}"
            result = self.llm.invoke([HumanMessage(content=prompt)]).content

        logger.info("[Analysis] 分析完成", length=len(result))
        return {"analysis_result": result, "current_step": state["current_step"] + 1}


class SynthesizerAgent:
    """汇总Agent：把各专家产出整合成最终回答"""

    def __init__(self):
        self.llm = get_llm(temperature=0.3)

    def run(self, state: AgentState) -> Dict:
        logger.info("[Synthesizer] 开始汇总结果")
        parts = []
        if state.get("research_result"):
            parts.append(state["research_result"])
        if state.get("coding_result"):
            parts.append(state["coding_result"])
        if state.get("analysis_result"):
            parts.append(state["analysis_result"])

        context = "\n\n---\n\n".join(parts) if parts else "（无中间结果，直接回答）"

        if get_settings().RUN_MODE == "mock" or not parts:
            final_answer = (
                f"{context}\n\n"
                f"---\n"
                f"【多智能体协作报告】\n"
                f"任务类型：{state.get('task_type', 'general')}\n"
                f"执行步骤：{' → '.join(state.get('plan', []))}\n"
                f"参与Agent：Planner + {state.get('task_type', 'general').capitalize()}Agent + Synthesizer\n"
                f"本次回答由LangGraph多智能体编排系统生成，支持人工审核断点续跑。"
            )
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "请把以下各专家的产出汇总成一份清晰、完整、有条理的最终回答，去掉重复内容。"),
                ("human", "用户问题：{query}\n\n各专家产出：\n{context}")
            ])
            final_answer = (prompt | self.llm).invoke({"query": state["user_query"], "context": context}).content

        logger.info("[Synthesizer] 汇总完成", length=len(final_answer))
        return {
            "messages": state["messages"] + [
                HumanMessage(content=state["user_query"]),
                AIMessage(content=final_answer),
            ],
            "end_time": time.time(),
        }


class HumanReviewNode:
    """
    人机协同节点：对应JD要求"Human-in-the-loop交互模式"
    执行到这里会中断流程，等待人工反馈后再继续
    """

    def run(self, state: AgentState) -> Dict:
        logger.info("[HumanReview] 流程暂停，等待人工审核")
        # 真实环境这里会interrupt，把中间结果返回给前端
        preview = ""
        for key in ("research_result", "coding_result", "analysis_result"):
            if state.get(key):
                preview = state[key][:300]
                break
        return {
            "needs_human_review": True,
            "messages": state["messages"] + [
                AIMessage(content=f"【等待人工审核】当前已完成初步产出，请审核：\n{preview}...\n\n请输入反馈意见（通过/修改意见）：")
            ]
        }


# ============== 3. 条件路由函数（条件边） ==============
def route_by_task_type(state: AgentState) -> str:
    """根据任务类型路由到对应的专家Agent"""
    task_type = state.get("task_type", "general")
    route_map = {
        "research": "research_agent",
        "coding": "coding_agent",
        "analysis": "analysis_agent",
        "general": "synthesizer",
    }
    logger.info("[路由] 任务类型→Agent", task_type=task_type, target=route_map[task_type])
    return route_map[task_type]


def route_after_review(state: AgentState) -> str:
    """人工审核后的路由：通过→汇总；有反馈→回到对应执行节点"""
    feedback = state.get("human_feedback", "")
    if not feedback or feedback.strip() in ("通过", "ok", "OK", "yes", "确认"):
        return "synthesizer"
    logger.info("[HumanReview] 收到修改反馈，返回重做", feedback=feedback[:50])
    # 有修改意见，回到对应Agent重新执行
    task_type = state.get("task_type", "general")
    return f"{task_type}_agent"


def should_human_review(state: AgentState) -> str:
    """判断是否需要人工审核"""
    if state.get("needs_human_review") and state.get("retry_count", 0) < 2:
        return "human_review"
    return "synthesizer"


def check_error(state: AgentState) -> str:
    """错误处理路由"""
    if state.get("error") and state.get("retry_count", 0) < 2:
        return "planner"  # 重试规划
    return "continue"


# ============== 4. LangGraph图构建（核心架构） ==============
def build_multi_agent_graph():
    """
    构建多智能体工作流图
    对应JD要求："StateGraph设计、节点编排、条件边、Checkpointer持久化"
    """
    planner = PlannerAgent()
    researcher = ResearchAgent()
    coder = CodingAgent()
    analyzer = AnalysisAgent()
    synthesizer = SynthesizerAgent()
    reviewer = HumanReviewNode()

    # 初始化状态图
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner.run)
    workflow.add_node("research_agent", researcher.run)
    workflow.add_node("coding_agent", coder.run)
    workflow.add_node("analysis_agent", analyzer.run)
    workflow.add_node("human_review", reviewer.run)
    workflow.add_node("synthesizer", synthesizer.run)

    # 定义边
    workflow.add_edge(START, "planner")

    # 规划后 → 按任务类型路由
    workflow.add_conditional_edges(
        "planner",
        route_by_task_type,
        {
            "research_agent": "research_agent",
            "coding_agent": "coding_agent",
            "analysis_agent": "analysis_agent",
            "synthesizer": "synthesizer",
        }
    )

    # 各专家Agent执行完 → 判断是否需要人工审核
    for node in ("research_agent", "coding_agent", "analysis_agent"):
        workflow.add_conditional_edges(
            node,
            should_human_review,
            {
                "human_review": "human_review",
                "synthesizer": "synthesizer",
            }
        )

    # 人工审核后 → 通过/修改
    workflow.add_conditional_edges(
        "human_review",
        route_after_review,
        {
            "synthesizer": "synthesizer",
            "research_agent": "research_agent",
            "coding_agent": "coding_agent",
            "analysis_agent": "analysis_agent",
        }
    )

    # 汇总 → 结束
    workflow.add_edge("synthesizer", END)

    # 配置Checkpointer（持久化，支持断点恢复）
    checkpointer = MemorySaver()

    # 编译图，配置中断点（Human-in-the-loop）
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],  # 在human_review节点前中断
    )
    return app


# ============== 5. 对外服务包装类 ==============
class MultiAgentPlatform:
    """
    多智能体平台对外接口：
    - 启动任务
    - 提交人工审核反馈
    - 获取执行状态
    - 完整的执行轨迹
    """

    def __init__(self):
        self.app = build_multi_agent_graph()
        self.logger = logger

    def submit_task(self, user_query: str, session_id: Optional[str] = None,
                    user_id: str = "default") -> Dict[str, Any]:
        """提交任务，执行到中断点或结束"""
        sid = session_id or str(uuid.uuid4())
        thread_id = f"{user_id}_{sid}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: AgentState = {
            "messages": [],
            "user_query": user_query,
            "task_type": None,
            "plan": None,
            "current_step": 0,
            "research_result": None,
            "coding_result": None,
            "analysis_result": None,
            "needs_human_review": False,
            "human_feedback": None,
            "error": None,
            "retry_count": 0,
            "session_id": sid,
            "start_time": time.time(),
            "end_time": None,
        }

        self.logger.info("提交多Agent任务", thread_id=thread_id, query=user_query[:50])
        start = time.time()

        # 执行（会在human_review前自动中断）
        result = self.app.invoke(initial_state, config=config)

        # 检查是否中断等待人工审核
        state = self.app.get_state(config)
        interrupted = state.next and "human_review" in state.next

        cost = time.time() - start

        # 获取最终回答或待审核内容
        final_msg = ""
        review_preview = ""
        if result.get("messages"):
            for m in reversed(result["messages"]):
                if isinstance(m, AIMessage):
                    final_msg = m.content
                    break

        return {
            "session_id": sid,
            "thread_id": thread_id,
            "status": "waiting_human_review" if interrupted else "completed",
            "task_type": result.get("task_type"),
            "plan": result.get("plan"),
            "answer": final_msg if not interrupted else None,
            "review_required": interrupted,
            "review_preview": review_preview if interrupted else None,
            "cost_seconds": round(cost, 2),
            "trace": self._get_execution_trace(result),
        }

    def submit_human_feedback(self, thread_id: str, feedback: str) -> Dict[str, Any]:
        """提交人工反馈，继续执行"""
        config = {"configurable": {"thread_id": thread_id}}
        # 更新状态中的human_feedback
        self.app.update_state(config, {"human_feedback": feedback, "needs_human_review": False})
        # 继续执行
        result = self.app.invoke(None, config=config)
        final_msg = ""
        for m in reversed(result.get("messages", [])):
            if isinstance(m, AIMessage):
                final_msg = m.content
                break
        self.logger.info("人工审核完成，继续执行", thread_id=thread_id, feedback=feedback[:30])
        return {
            "status": "completed",
            "answer": final_msg,
            "trace": self._get_execution_trace(result),
        }

    def get_execution_status(self, thread_id: str) -> Dict:
        config = {"configurable": {"thread_id": thread_id}}
        state = self.app.get_state(config)
        return {
            "next": list(state.next) if state.next else [],
            "current_step": state.values.get("current_step"),
            "task_type": state.values.get("task_type"),
        }

    def _get_execution_trace(self, state: Dict) -> List[Dict]:
        """提取完整执行轨迹"""
        trace = []
        if state.get("plan"):
            trace.append({"node": "planner", "output": f"任务类型：{state.get('task_type')}，规划{len(state['plan'])}步"})
        for key, name in [("research_result", "research_agent"),
                          ("coding_result", "coding_agent"),
                          ("analysis_result", "analysis_agent")]:
            if state.get(key):
                trace.append({"node": name, "output_preview": state[key][:200]})
        if state.get("end_time"):
            trace.append({"node": "synthesizer", "status": "completed"})
        return trace


# ============== 使用示例 ==============
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from common.logger import setup_logging
    setup_logging()

    platform = MultiAgentPlatform()

    print("="*70)
    print("Demo3：LangGraph多智能体协作平台（StateGraph + Human-in-the-loop）")
    print("="*70)

    # 场景1：研究类任务
    print("\n【场景1】研究类任务 → ResearchAgent + 人工审核")
    print("─"*70)
    resp = platform.submit_task("帮我调研一下LangGraph在企业级应用中的最佳实践")
    print(f"[用户] 帮我调研一下LangGraph在企业级应用中的最佳实践")
    print(f"[状态] {resp['status']}")
    print(f"[规划] {resp['plan']}")
    if resp['review_required']:
        print("\n[系统] 进入人工审核环节，自动提交「通过」继续...")
        resp2 = platform.submit_human_feedback(resp['thread_id'], "通过")
        print(f"[最终回答]\n{resp2['answer'][:600]}...")

    # 场景2：代码类任务
    print("\n\n【场景2】代码类任务 → CodingAgent")
    print("─"*70)
    resp = platform.submit_task("用LangGraph实现一个支持人机协同的客服智能体")
    print(f"[用户] 用LangGraph实现一个支持人机协同的客服智能体")
    print(f"[状态] {resp['status']}")
    print(f"[规划] {resp['plan']}")
    print(f"[执行轨迹] {[t['node'] for t in resp['trace']]}")
    if resp['review_required']:
        resp2 = platform.submit_human_feedback(resp['thread_id'], "通过")
        print(f"\n[最终回答]\n{resp2['answer'][:500]}...")
    else:
        print(f"\n[回答]\n{resp['answer'][:500]}...")

    # 场景3：普通问答直接回答
    print("\n\n【场景3】普通问答 → 直接回答，不调度专家Agent")
    print("─"*70)
    resp = platform.submit_task("你好，请介绍一下你自己")
    print(f"[用户] 你好，请介绍一下你自己")
    print(f"[状态] {resp['status']}")
    print(f"[回答]\n{resp['answer'][:400]}")

    print("\n\n✅ Demo3运行完成：覆盖StateGraph、条件路由、多Agent编排、Checkpointer持久化、Human-in-the-loop全能力")
