"""
Phase 2 测试：Tool Use / Function Calling
=========================================

核心概念：
1. bind_tools()：把工具"绑定"给 LLM，LLM 拿到工具的名称、参数、描述
   ≈ 告诉 LLM "你有这些技能可以用"

2. LLM 不会直接执行工具，它只会输出"我想调用 XX 工具，参数是 XX"
   真正执行工具的是你的 Python 代码（tool_executor）

3. 这就是 Agent 的雏形：LLM 决策 → 工具执行 → 结果反馈给 LLM → 生成回答

运行方法：
  venv\\Scripts\\activate
  python test_tool_use.py

测试问题建议：
  - "北京今天天气怎么样"    → 应该调 get_weather
  - "成都有什么好玩的地方"   → 应该调 search_travel_info
  - "西安的天气和景点介绍"   → 可能同时调两个工具
  - "你叫什么名字"          → 不调任何工具，直接回答
"""

import os

# 修复 conda 环境下 SSL_CERT_FILE 冲突问题
# conda 会设置此变量指向自己的证书，导致 httpx 初始化失败
os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage

from tools.weather import get_weather
from tools.search import search_travel_info

load_dotenv()

# ── 初始化 LLM ──────────────────────────────────────────────
# 注意：这里用 langchain_openai 的 ChatOpenAI，不是直接用 openai 库
# 区别：langchain 的封装支持 bind_tools、流式等高级功能
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0.7,
)

# ── 绑定工具 ─────────────────────────────────────────────────
# bind_tools 把工具列表传给 LLM，LLM 下次回复时可以选择调用
tools = [get_weather, search_travel_info]
llm_with_tools = llm.bind_tools(tools)

# 工具名 → 函数 的映射表，用于实际执行
tool_map = {
    "get_weather": get_weather,
    "search_travel_info": search_travel_info,
}

# 系统提示词
system_prompt = SystemMessage(content="""你是一个专业的旅行规划助手。
你有以下工具可以使用：
- get_weather：查询城市天气
- search_travel_info：搜索景点/美食/攻略信息

请根据用户问题判断是否需要调用工具，需要时直接调用，不需要时直接回答。
获取工具结果后，整合成友好的中文回答。""")


def invoke_with_retry(llm_instance, messages, max_retries=2):
    """LLM 调用加重试，避免第一次冷连接失败"""
    for attempt in range(max_retries):
        try:
            return llm_instance.invoke(messages)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [连接失败，正在重试... ({attempt + 1}/{max_retries - 1})]")
            else:
                raise e


def chat_with_tools(user_input: str):
    """
    带工具调用的对话函数

    流程：
    1. 用户输入 → LLM（可能决定调工具）
    2. 如果 LLM 要调工具 → 执行工具 → 把结果返回给 LLM
    3. LLM 整合工具结果 → 生成最终回答
    """
    messages = [system_prompt, HumanMessage(content=user_input)]

    print(f"\n{'='*50}")
    print(f"用户：{user_input}")
    print(f"{'='*50}")

    # 第一轮：LLM 决策（可能返回工具调用请求）
    response = invoke_with_retry(llm_with_tools, messages)

    # 检查 LLM 是否要调用工具
    if response.tool_calls:
        print(f"\n[LLM 决定调用工具]")
        messages.append(response)  # 把 LLM 的决策加入历史

        # 执行所有工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            print(f"  → 调用工具：{tool_name}，参数：{tool_args}")

            # 实际执行工具
            tool_func = tool_map.get(tool_name)
            if tool_func:
                tool_result = tool_func.invoke(tool_args)
            else:
                tool_result = f"未知工具：{tool_name}"

            print(f"  → 工具返回（前100字）：{str(tool_result)[:100]}...")

            # 把工具结果加入消息历史（LangChain 用 ToolMessage 表示工具执行结果）
            # ≈ 把工具结果"告诉"LLM，让它整合进最终回答
            messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)
            )

        # 第二轮：LLM 整合工具结果，生成最终回答
        # 注意：这里用 llm（不带工具），强制 LLM 直接生成回答，而不是再次调工具
        print(f"\n[LLM 整合结果，生成回答]")
        final_response = invoke_with_retry(llm, messages)
        print(f"\n助手：{final_response.content}")

    else:
        # LLM 直接回答，不需要工具
        print(f"\n[LLM 直接回答，无需工具]")
        print(f"\n助手：{response.content}")


# ── 主程序 ───────────────────────────────────────────────────
print("旅行助手（工具版）已启动，输入 quit 退出")
print("建议测试问题：")
print("  1. 北京今天天气怎么样")
print("  2. 成都有什么好玩的地方")
print("  3. 西安的天气和景点介绍")
print()

while True:
    user_input = input("你：").strip()
    if not user_input:
        continue
    if user_input.lower() == "quit":
        break
    chat_with_tools(user_input)
