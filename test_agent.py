"""
Phase 3 测试：LangGraph Agent
==============================

和 Phase 2 的区别：
- Phase 2：你手动写了"第一轮 → 执行工具 → 第二轮"
- Phase 3：LangGraph 自动循环，直到 LLM 不再调工具为止

运行方法：
  venv\\Scripts\\activate
  python test_agent.py
"""

import os
os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

from langchain_core.messages import HumanMessage
from agent.graph import agent


def chat(user_input: str):
    print(f"\n{'='*50}")
    print(f"用户：{user_input}")
    print(f"{'='*50}")

    # invoke 传入初始 State：只有用户的第一条消息
    result = agent.invoke({"messages": [HumanMessage(content=user_input)]})

    # result["messages"] 是完整的消息历史，最后一条是 LLM 的最终回答
    final_message = result["messages"][-1]
    print(f"\n助手：{final_message.content}")


print("旅行助手（LangGraph Agent 版）已启动，输入 quit 退出")
print()

while True:
    user_input = input("你：").strip()
    if not user_input:
        continue
    if user_input.lower() == "quit":
        break
    chat(user_input)
