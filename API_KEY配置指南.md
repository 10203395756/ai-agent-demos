# 🔑 API Key 配置与真实大模型切换指南

> 本工程默认以 **Mock 模式**启动（不需要任何 Key、不联网即可演示）。
> 当你要在面试里演示真实大模型能力，或用于实际项目时，按下面配置。

---

## 🚀 一、3步切到真实大模型

### 第1步：复制配置文件
在项目根目录下操作：

```bash
# Windows 命令行
copy .env.example .env

# Linux/Mac/Git Bash
cp .env.example .env
```

### 第2步：编辑 `.env`，填写你选的厂商 Key（4选1即可，推荐 DeepSeek 性价比最高）

#### ✅ 推荐：DeepSeek（最便宜，代码/Agent 能力强，适合面试演示）
```env
RUN_MODE=real
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx     # 在 https://platform.deepseek.com/ 申请
DEEPSEEK_MODEL=deepseek-chat                      # 或 deepseek-reasoner（R1 推理模型）
```
- 注册送额度，充值 10 元足够演示几十次
- Base URL 默认指向官方，支持国内网络直连

#### ✅ 百度文心一言（国内最稳定、企业常用）
```env
RUN_MODE=real
LLM_PROVIDER=qianfan
QIANFAN_AK=xxxxxxxxxxxxxxxx         # API Key，在 https://console.bce.baidu.com/qianfan/ 获取
QIANFAN_SK=xxxxxxxxxxxxxxxx         # Secret Key
QIANFAN_MODEL=ernie-4.0-turbo-8k
```

#### ✅ 阿里通义千问
```env
RUN_MODE=real
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxxxxxxx       # 在 https://dashscope.console.aliyun.com/ 获取
DASHSCOPE_MODEL=qwen-plus
```

#### ✅ OpenAI / 兼容接口（包括第三方代理、Azure、OpenRouter 等）
```env
RUN_MODE=real
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1    # 第三方代理改这里
OPENAI_MODEL=gpt-4o-mini                     # 性价比首选
```

### 第3步：重启服务
- Windows：双击 `start.bat` 或在 cmd 里运行 `start.bat`
- Linux/Mac：`bash start.sh`
- 看到日志里 `✅ LLM 已初始化: xxx (real模式)` 就成功了

---

## 🎯 二、不同场景的 Key 推荐

| 场景 | 推荐 | 原因 |
|------|------|------|
| 面试现场演示（求稳、怕出问题） | **文心一言 / 通义千问** | 国内网络直连，延迟低，不会被墙 |
| 面试现场演示（要体现技术深度） | **DeepSeek** | R1 推理模型展示 Chain-of-Thought 效果惊艳 |
| 做项目长期使用 / 成本敏感 | **DeepSeek / gpt-4o-mini** | 输入百万 token 只要 1-2 元人民币 |
| 要跑 OpenAI 生态（Function Calling / Structured Output） | **gpt-4o-mini** | 兼容性最好 |

---

## 🧪 三、怎么验证 Key 配好了？

启动服务后：

1. 看启动日志：应该显示 `LLM 已初始化: deepseek (real模式)` 而不是 `mock模式`
2. 访问 http://localhost:8000/health ，返回 JSON 里 `"llm_mode": "real"`
3. 在 Swagger（http://localhost:8000/docs）里调用 `/api/v1/demo1/chat`，输入任意问题，看返回的 answer 是否是真实模型回答而非 Mock 模板

如果报错 401：Key 填错了；报错 429：免费额度用完或速率限制；报错超时：网络不通，建议换国内厂商。

---

## 🔒 四、安全提醒（简历/GitHub 提交必读）

1. **`.env` 已经写在 `.gitignore` 里**，不会被提交到 GitHub——**不要手贱把它加到 git**
2. 简历里放 GitHub 链接前，先去仓库 Settings → Secrets 确认没有泄露 Key
3. 如果不小心把 Key 提交过，立刻去对应厂商控制台**作废并重新生成**
4. 面试演示前在本地跑一次，确认 Key 可用、余额充足（别现场翻车）

---

## 💡 五、零成本/无 Key 的应对方案

如果你的电脑完全没网、也不想申请 Key：
- **直接用默认 Mock 模式面试演示完全够用**——核心演示的是 **架构能力、工具注册机制、状态机编排、人机协同**，这些都是代码层面的东西，面试官关心的是你能不能讲清设计思路，不会盯着你接的是真模型还是 Mock
- 面试话术：「为了现场稳定我用的是 Mock LLM，实际接入只需要改一行配置（演示 .env 切换），生产环境我一般接 DeepSeek 做主力、文心做降级兜底」——这句话非常加分，体现了工程思维。
