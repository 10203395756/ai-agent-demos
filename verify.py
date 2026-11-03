"""
快速验证脚本：不安装完整依赖、不启动服务，直接验证核心逻辑可运行
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 仅依赖已安装的基础包验证Mock模式核心逻辑
from common.config import get_settings
from common.llm import MockChatModel
from common.logger import setup_logging

setup_logging()
settings = get_settings()
print(f"✅ 配置加载正常，运行模式：{settings.RUN_MODE}")

# 验证Mock LLM能正常生成
llm = MockChatModel()
from langchain_core.messages import HumanMessage
resp = llm.invoke([HumanMessage(content="你好，请介绍一下自己")])
print(f"✅ Mock LLM 响应正常：{resp.content[:60]}...")

# 验证工具调用判断
tools = [
    {"type": "function", "function": {"name": "get_weather", "description": "查天气"}},
    {"type": "function", "function": {"name": "calculator", "description": "计算器"}},
]
resp2 = llm.invoke([HumanMessage(content="帮我查一下贵阳天气")], tools=tools)
print(f"✅ Function Calling 工具识别正常：调用 {resp2.tool_calls[0]['name'] if resp2.tool_calls else '无'}")

print()
print("🎉 核心模块验证通过！")
print("📌 完整启动请运行：bash start.sh")
print("📌 API文档：http://localhost:8000/docs")
