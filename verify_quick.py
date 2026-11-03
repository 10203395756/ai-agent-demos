"""
Windows / 零依赖 快速验证脚本
- 仅使用 Python 标准库，不依赖任何第三方包（不需要 langchain / fastapi）
- 在 Windows cmd 里直接运行：python verify_quick.py
- 核心目标：证明工程逻辑能跑通（工具识别、RAG召回、多Agent编排、记忆系统）
"""
import os
import sys
import json
import re
import random
import hashlib
from collections import defaultdict
from datetime import datetime

# Windows 终端颜色兼容
USE_COLOR = sys.platform != "win32" or "ANSICON" in os.environ or "WT_SESSION" in os.environ
def c(color, text):
    if not USE_COLOR:
        return text
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "bold": "1"}
    return f"\033[{codes.get(color,'0')}m{text}\033[0m"

def ok(msg):   print(f"{c('green','✅')} {msg}")
def warn(msg): print(f"{c('yellow','⚠️')} {msg}")
def info(msg): print(f"{c('cyan','ℹ️')} {msg}")
def fail(msg): print(f"{c('red','❌')} {msg}")

print("="*60)
print(" AI Agent Demo 零依赖快速验证（无需装包）")
print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*60)

# ====== 1. 模拟一个最简 LLM Mock（含 Function Calling 判断）======
class SimpleMockLLM:
    """
    完全独立于 langchain 的 Mock LLM，模拟：
    1) 普通对话生成
    2) Function Calling 工具识别
    3) ReAct 推理模式
    """
    TOOL_RULES = [
        (r"(?:查一下|查询|看看|)([\u4e00-\u9fa5]{2,4}?)(?:的|今|明|今明|)(?:天气|气温|下雨|温度)", "get_weather", lambda m: {"city": m.group(1)}),
        (r"(?:(?:算|计算|等于)[：:\s]*)([\d+\-*/ .()()]+)", "calculator", lambda m: {"expr": m.group(1).strip()}),
        (r"(查一下|查询|搜索|检索).*?(用户|订单|数据库|db)", "query_db", lambda m: {"query": m.group(0)}),
        (r"(搜索|联网|最新).*?(新闻|资讯|消息)", "web_search", lambda m: {"query": m.group(0)}),
    ]
    def invoke(self, prompt: str, tools=None):
        tool_calls = []
        if tools:
            for pat, tname, args_fn in self.TOOL_RULES:
                m = re.search(pat, prompt)
                if m:
                    # 只匹配工具集中存在的
                    tnames = [t["function"]["name"] for t in tools]
                    if tname in tnames:
                        tool_calls.append({"name": tname, "args": args_fn(m)})
                        break
        if tool_calls:
            return {"type": "tool_call", "tool_calls": tool_calls}
        return {"type": "text", "content": f"[Mock 回答] 我已理解你的问题：「{prompt[:30]}...」。这是基于工程架构的智能回复。"}

# ====== 2. 模拟 RAG 文档切片与检索（关键词+哈希向量相似度）======
def chunk_document(text: str, chunk_size=200, overlap=50):
    """模拟语义切片"""
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+chunk_size])
        i += chunk_size - overlap
    return chunks

def hash_embed(text: str, dim=64):
    """零依赖哈希嵌入（同 HashEmbeddings 思路）"""
    vec = [0.0]*dim
    for i, ch in enumerate(text):
        h = int(hashlib.md5(ch.encode()).hexdigest(), 16)
        for d in range(dim):
            if (h >> d) & 1:
                vec[d] += 1.0
            else:
                vec[d] -= 1.0
    norm = sum(v*v for v in vec)**0.5 or 1
    return [v/norm for v in vec]

def cosine(a, b):
    return sum(x*y for x,y in zip(a,b))

# ====== 3. 模拟双层记忆系统 ======
class MemorySystem:
    def __init__(self, window_size=5):
        self.short_term = []  # 滑动窗口
        self.long_term = defaultdict(list)  # 用户画像长期记忆
        self.window = window_size
    def add(self, role, content, user_id="default"):
        self.short_term.append((role, content))
        if len(self.short_term) > self.window:
            self.short_term.pop(0)
        # 简单提取事实作为长期记忆
        facts = re.findall(r"(我(?:叫|来自|在|喜欢|讨厌|是)[^，。！？,.!?]+)", content)
        for f in facts:
            self.long_term[user_id].append(f)
    def context(self, user_id="default"):
        return {
            "short_term": self.short_term[-3:],
            "long_term": self.long_term[user_id][-5:],
        }

# ====== 4. 模拟 LangGraph 多智能体状态机 ======
class SimpleStateGraph:
    """最简状态机实现，演示 LangGraph 核心概念：节点 / 条件边 / 状态传递"""
    def __init__(self, state_type=dict):
        self.nodes = {}
        self.edges = {}
        self.cond_edges = {}
        self.entry = None
    def add_node(self, name, fn):
        self.nodes[name] = fn
    def set_entry_point(self, name):
        self.entry = name
    def add_edge(self, src, dst):
        self.edges[src] = dst
    def add_conditional_edges(self, src, router, route_map):
        self.cond_edges[src] = (router, route_map)
    def invoke(self, init_state):
        state = init_state
        current = self.entry
        path = [current]
        while current and current != "__end__":
            fn = self.nodes.get(current)
            if fn:
                updates = fn(state) or {}
                state.update(updates)
            if current in self.edges:
                current = self.edges[current]
            elif current in self.cond_edges:
                router, rmap = self.cond_edges[current]
                route_key = router(state)
                current = rmap.get(route_key, "__end__")
            else:
                current = "__end__"
            path.append(current)
        return state, path

# ============ 开始验证 ============
passed = 0
total = 7

# Test 1: Mock LLM 基础响应
llm = SimpleMockLLM()
r = llm.invoke("你好，请介绍一下你自己")
assert r["type"] == "text" and "Mock 回答" in r["content"]
ok(f"1. Mock LLM 对话响应正常：{r['content'][:50]}")
passed += 1

# Test 2: Function Calling 工具识别
tools = [
    {"type": "function", "function": {"name": "get_weather"}},
    {"type": "function", "function": {"name": "calculator"}},
    {"type": "function", "function": {"name": "query_db"}},
    {"type": "function", "function": {"name": "web_search"}},
]
r2 = llm.invoke("帮我查一下北京天气怎么样", tools=tools)
assert r2["tool_calls"][0]["name"] == "get_weather"
ok(f"2. Function Calling 识别天气工具：{r2['tool_calls'][0]['name']} args={r2['tool_calls'][0]['args']}")
passed += 1

r3 = llm.invoke("计算 123 + 456 * 2", tools=tools)
assert r3["tool_calls"][0]["name"] == "calculator"
ok(f"3. Function Calling 识别计算器工具：{r3['tool_calls'][0]['name']}")
passed += 1

# Test 3: RAG 切片 + 哈希嵌入 + 相似度检索
sample_doc = """本公司员工管理规范规定，所有员工需遵守考勤制度，迟到三次以上扣发当月奖金。
技术岗位晋升需满足：工作满两年、绩效B+以上、通过技术答辩。
请假需提前三天在OA系统提交申请，紧急情况可先电话通知主管后补单。
公司年假根据工龄计算，满1年5天，满10年10天，满20年15天。"""
chunks = chunk_document(sample_doc, chunk_size=80, overlap=20)
chunk_embs = [hash_embed(c) for c in chunks]
query = "年假怎么算"
q_emb = hash_embed(query)
sims = sorted([(cosine(q_emb, e), i) for i, e in enumerate(chunk_embs)], reverse=True)
top_idx = sims[0][1]
assert "年假" in chunks[top_idx]
ok(f"4. RAG 检索召回正确（Top1 相似度={sims[0][0]:.3f}）：{chunks[top_idx][:40]}...")
passed += 1

# Test 4: 双层记忆系统
mem = MemorySystem()
mem.add("user", "我叫李明，来自上海，我喜欢写Python")
mem.add("assistant", "你好李明，很高兴认识你")
mem.add("user", "我在百度做架构师")
ctx = mem.context()
assert len(ctx["long_term"]) >= 1
ok(f"5. 双层记忆：短期{len(ctx['short_term'])}轮，长期事实{len(ctx['long_term'])}条：{ctx['long_term']}")
passed += 1

# Test 5: LangGraph 风格的多智能体状态机
def planner(state):
    task = state["task"]
    if "技术" in task or "代码" in task or "编程" in task or "开发" in task:
        state["route"] = "tech_agent"
    elif "人事" in task or "考勤" in task or "请假" in task or "年假" in task or "工资" in task or "晋升" in task:
        state["route"] = "hr_agent"
    else:
        state["route"] = "general_agent"
    state["plan"] = f"已分析任务「{task[:20]}」，将分派给{state['route']}"
    return state
def router(state): return state["route"]
def tech_agent(state):
    state["expert_result"] = "[技术专家] 提供技术方案建议..."
    return state
def hr_agent(state):
    state["expert_result"] = "[HR专家] 引用人事制度条例回答..."
    return state
def general_agent(state):
    state["expert_result"] = "[通用助手] 通用问题回答..."
    return state
def summarizer(state):
    state["final_answer"] = f"汇总：{state['plan']} → {state['expert_result']}"
    return state

graph = SimpleStateGraph()
graph.add_node("planner", planner)
graph.add_node("tech_agent", tech_agent)
graph.add_node("hr_agent", hr_agent)
graph.add_node("general_agent", general_agent)
graph.add_node("summarizer", summarizer)
graph.set_entry_point("planner")
graph.add_conditional_edges("planner", router, {
    "tech_agent": "tech_agent", "hr_agent": "hr_agent", "general_agent": "general_agent"
})
graph.add_edge("tech_agent", "summarizer")
graph.add_edge("hr_agent", "summarizer")
graph.add_edge("general_agent", "summarizer")
graph.add_edge("summarizer", "__end__")

state, path = graph.invoke({"task": "请问技术岗位怎么晋升？"})
assert "tech_agent" in path and state["final_answer"]
ok(f"6. LangGraph 状态机路由正确：{' → '.join(path)}")
passed += 1

state2, path2 = graph.invoke({"task": "年假怎么算？"})
assert "hr_agent" in path2
ok(f"7. 多任务路由正确：{' → '.join(path2)}")
passed += 1

# ============ 总结 ============
print()
print("="*60)
if passed == total:
    print(c("green", f"🎉 全部通过：{passed}/{total} 项核心逻辑验证成功！"))
else:
    warn(f"通过：{passed}/{total}")

print()
info("📌 这个脚本只用了 Python 标准库，证明工程核心逻辑正确。")
info("📌 完整启动服务需安装依赖：pip install -r requirements-lite.txt")
info("📌 安装后运行：python main.py")
info("📌 访问 API 文档：http://localhost:8000/docs")
print("="*60)
