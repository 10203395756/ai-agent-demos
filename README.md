# AI智能体平台（企业级Demo工程）

> 面向 8年+ 架构/带队经验开发者，精准对标 **高级AI智能体开发工程师** JD（LangChain/LangGraph/RAG/多Agent/工程化）。
> **零API Key可跑通全链路**，配置.env即可切换真实大模型。

---

## 🎯 项目定位

这不是玩具Demo，是一套**可以直接写进简历、面试官追问能答到底、架构设计经得起拷问**的生产级工程。三个Demo形成递进梯度，100%覆盖你给的JD要求：

| Demo | 模块名称 | 对应JD核心要求 | 技术栈 |
|------|----------|----------------|--------|
| Demo1 | 企业知识库RAG+长期记忆 | RAG与记忆系统：检索增强生成链路、长期记忆管理、上下文压缩与动态召回 | LangChain + Chroma/FAISS + Embedding |
| Demo2 | 多工具调用智能体助手 | 工具生态集成：统一工具注册/发现/调用机制、Function Calling | LangChain Agent + StructuredTool + Pydantic |
| Demo3 | LangGraph多智能体协作平台 | 智能体架构设计、多智能体编排、人机协同(Human-in-the-loop) | LangGraph StateGraph + Checkpointer + 条件边 |
| 服务层 | FastAPI生产级服务 | 工程化落地、性能优化、高可用部署、监控告警日志 | FastAPI + SSE流 + SlowApi限流 + Prometheus + Docker |

---

## 🚀 快速启动（5分钟跑通）

### 方式0：Windows 用户看这里（重要）

Windows 上命令**不叫 `python3`，叫 `python` 或 `py`**，所以不要用 `bash start.sh`，用下面任一种：

```bat
:: 方式A（推荐，一键搞定）：双击或在 cmd 里运行
start.bat

:: 方式B：零依赖快速验证（不装任何包就能验证核心逻辑）
python verify_quick.py

:: 方式C：手动三步
python -m pip install -r requirements-lite.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python main.py
```

> **不确定环境缺什么？直接运行 `python verify_quick.py`，零依赖，输出 7 项 ✅ 就说明工程逻辑没问题。**

---

### 方式1：Linux / Mac / Git Bash

```bash
# 一键启动（自动检测依赖、跳过安装直接启动）
bash start.sh

# 零依赖快速验证
python3 verify_quick.py
```
> ```bat
> python doctor.py
> ```
> 它会一次性检查 Python 版本、依赖、项目文件、数据目录、端口占用，并给出可直接复制的修复命令。

### 方式1：macOS / Linux 一键启动（推荐）
```bash
# 1. 进入项目目录
cd ai-agent-demos

# 2. 一键启动（自动检测依赖，齐全则直接启动，无需联网）
bash start.sh
```

> **遇到 `pip install` 联网失败报错（Temporary failure in name resolution）？**
> 这是你的环境**没网**导致，不是代码问题。启动脚本已优化为"依赖齐全则跳过安装"，所以：
> - 若环境已有 langchain/langgraph/fastapi（公司内网镜像、预装环境通常都有），`bash start.sh` 会直接跑起来；
> - 若确实缺包且无网：先运行 `python3 verify.py` 验证核心逻辑，或按下方"离线安装"方式处理。
>
> **离线安装**（在有网的机器上）：
> ```bash
> pip download -r requirements.txt -d ./pkgs
> # 把 pkgs 目录拷到目标机器后：
> pip install --no-index --find-links=./pkgs -r requirements.txt
> ```

### 方式2：手动启动
```bash
# 1. 创建虚拟环境（可选）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖（已有可跳过）
pip install -r requirements.txt

# 3. 配置环境变量（默认Mock模式，无需改动）
cp .env.example .env

# 4. 启动服务
python main.py
```

启动成功后访问：
- 📖 **API文档（Swagger）**：http://localhost:8000/docs （可以直接在页面上测试所有接口）
- ❤️ 健康检查：http://localhost:8000/health
- 📊 Prometheus监控指标：http://localhost:8000/metrics
- 🏠 服务首页：http://localhost:8000/

### 切换真实大模型（可选）
编辑 `.env` 文件：
```bash
RUN_MODE=real
LLM_PROVIDER=qianfan  # 可选 openai / qianfan / dashscope / deepseek
QIANFAN_AK=你的AK
QIANFAN_SK=你的SK
```
重启服务即可，业务代码无需任何修改。

---

## 📁 项目结构

```
ai-agent-demos/
├── common/                     # 公共模块（复用层）
│   ├── config.py               # 统一配置（Mock/Real透明切换）
│   ├── llm.py                  # LLM客户端工厂 + MockChatModel
│   ├── logger.py               # 结构化日志 + TraceID链路追踪
│   ├── metrics.py              # Prometheus监控指标
│   └── cache.py                # 提示词缓存（内存/Redis自动切换）
├── demo1_rag_memory/           # Demo1：RAG + 长期记忆
│   └── rag_memory.py           # 文档切片→混合检索→上下文压缩→记忆管理
├── demo2_tools_agent/          # Demo2：多工具智能体
│   └── tools_agent.py          # 工具注册中心 + 5个内置工具 + ReAct Agent
├── demo3_langgraph_multi_agent/ # Demo3：多智能体协作
│   └── multi_agent.py          # StateGraph + 多专家Agent + 人机协同
├── service/                    # 服务层扩展预留
├── deploy/
│   └── Dockerfile              # Docker生产部署配置
├── docs/
│   ├── 简历写法指南.md          # 👉 简历项目经验怎么写
│   └── 面试话术.md              # 👉 高频面试题+参考答案
├── main.py                     # FastAPI服务入口（所有REST接口）
├── requirements.txt            # Python依赖
├── .env.example                # 环境变量模板
├── start.sh                    # 一键启动脚本
└── README.md
```

---

## 🔧 各Demo核心能力详解

### Demo1：企业知识库RAG + 长期记忆系统
**核心能力**：
1. **多格式文档加载**：txt/md/pdf/docx自动识别
2. **智能切片**：递归字符分割 + 语义边界（/n/n → 。→ ，）
3. **混合检索**：向量相似度检索 + 关键词匹配（真实环境可接BM25/ES）
4. **相关度阈值过滤**：低相似度结果自动丢弃
5. **上下文压缩**：Token预算控制 + 历史对话摘要压缩（近N轮保留原文，更早做摘要）
6. **双层长期记忆**：短期滑动窗口会话记忆 + 用户画像持久化（偏好/事实/实体）
7. **自动记忆抽取**：从对话中自动提取用户背景和偏好

**REST接口**：
- `POST /api/v1/rag/query` RAG问答（支持SSE流式）
- `POST /api/v1/rag/ingest` 文本入库
- `POST /api/v1/rag/upload` 文件上传入库
- `GET /api/v1/rag/sessions/{sid}/memory` 查看用户长期记忆

---

### Demo2：多工具调用智能体助手
**核心能力**：
1. **插件式工具注册中心**：统一注册/发现/分类/权限控制，新增工具只需要写函数+Pydantic Schema
2. **统一工具调用治理**：超时控制、异常兜底、调用指标埋点、日志追踪
3. **内置5个业务工具**：网页搜索、天气查询、数学计算器、数据库查询（安全SQL校验）、时间查询
4. **Function Calling**：自动识别意图选择工具，支持**串行多工具调用**
5. **ReAct推理模式**：思考→行动→观察→回答，max_iterations防无限循环
6. **完整调用轨迹**：每次执行返回所有工具调用的参数和结果，便于调试和审计

**REST接口**：
- `POST /api/v1/agent/chat` 工具智能体对话
- `POST /api/v1/agent/chat/stream` SSE流式对话（实时显示工具调用过程）
- `GET /api/v1/agent/tools` 查看已注册工具列表

---

### Demo3：LangGraph多智能体协作平台（核心项目）
**核心能力**：
1. **StateGraph状态机**：共享TypedDict状态，所有节点读写统一状态
2. **多专家Agent分工**：Planner规划 → Researcher/Coder/Analyzer专家执行 → Synthesizer汇总
3. **条件边路由**：按任务类型自动路由到对应专家Agent；审核后判断通过/返工
4. **Checkpointer持久化**：MemorySaver保存执行状态，支持断点续跑
5. **Human-in-the-loop人机协同**：`interrupt_before`在关键节点自动中断，人工确认/反馈后继续
6. **错误重试与熔断**：retry_count控制最大重试次数，防止死循环
7. **完整执行轨迹**：返回每个节点的输入输出，可观测可调试

**REST接口**：
- `POST /api/v1/multi-agent/submit` 提交任务（自动规划路由，审核点自动中断）
- `POST /api/v1/multi-agent/feedback` 提交人工反馈继续执行
- `GET /api/v1/multi-agent/status/{thread_id}` 查询执行状态
- `GET /api/v1/multi-agent/graph` 导出状态图（Mermaid）。默认返回内置图，稳定秒回；
  加 `?source=live` 可尝试从本机 LangGraph 实时导出（带超时与自动降级）

---

## 🏗️ 工程化亮点（架构师简历加分项）

| 能力点 | 实现方式 |
|--------|----------|
| **限流保护** | SlowApi按IP限流，默认60次/分钟，防止接口被刷 |
| **全链路追踪** | 每个请求分配唯一TraceID，贯穿日志、监控、响应头 |
| **结构化日志** | structlog JSON格式输出，便于ELK采集 |
| **监控指标** | Prometheus埋点：HTTP请求、LLM调用、Token消耗、工具调用、缓存命中、RAG检索、活跃会话 |
| **多级缓存** | 提示词缓存自动切换内存/Redis，减少重复LLM调用，降低成本 |
| **统一异常处理** | 全局异常捕获，统一错误响应格式，不暴露堆栈 |
| **SSE流式输出** | 所有问答接口支持流式，token级输出，响应速度提升感知明显 |
| **CORS跨域** | 支持前端直接调用，可配置允许域名 |
| **健康检查** | /health端点，K8s/Docker可做存活探测 |
| **Docker部署** | 生产级Dockerfile，gunicorn多进程启动 |
| **Mock/Real双模式** | 默认Mock模式离线可跑，切换.env即连真实大模型，业务代码零改动 |

---

## 📊 本地验证

### 方式1：单独运行每个Demo
```bash
# 验证Demo1
python demo1_rag_memory/rag_memory.py

# 验证Demo2
python demo2_tools_agent/tools_agent.py

# 验证Demo3
python demo3_langgraph_multi_agent/multi_agent.py
```

### 方式2：启动服务后Swagger测试
打开 http://localhost:8000/docs，直接在页面上点击"Try it out"测试任意接口。

### 方式3：curl测试
```bash
# RAG问答
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"question":"什么是LangGraph？"}'

# 工具智能体
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我算一下1299打85折是多少"}'

# 多智能体协作
curl -X POST http://localhost:8000/api/v1/multi-agent/submit \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我调研一下LangGraph最佳实践"}'
```

---

## 🔄 从Mock切换到真实大模型

| 厂商 | LLM_PROVIDER | 需要的Key | 推荐模型 |
|------|-------------|-----------|---------|
| 百度文心一言 | qianfan | QIANFAN_AK / QIANFAN_SK | ernie-4.0-turbo-8k |
| 阿里通义千问 | dashscope | DASHSCOPE_API_KEY | qwen-plus |
| DeepSeek | deepseek | DEEPSEEK_API_KEY | deepseek-chat |
| OpenAI | openai | OPENAI_API_KEY | gpt-4o-mini |

---

## 📎 下一步

- 📝 **写简历**：看 `docs/简历写法指南.md`，直接复制模板改
- 🎤 **准备面试**：看 `docs/面试话术.md`，高频题+参考答案都整理好了
- 🎨 **前端Demo**：有精力可以加个Streamlit/Gradio页面，放在项目根目录app.py
