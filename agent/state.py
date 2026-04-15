"""
Agent 状态定义
==============

State 是 LangGraph 里最基础的概念：
- 整个图（工作流）执行过程中，所有节点共享同一个 State
- 每个节点可以读取 State，也可以往 State 里添加数据
- 节点之间不直接传参，而是通过修改 State 来"交流"

Java 类比：State ≈ 一个在所有流程节点间传递的上下文对象（Context/VO）
"""

from typing import Annotated
from langgraph.graph import MessagesState


# MessagesState 是 LangGraph 内置的状态类
# 它已经帮你定义好了 messages 字段（消息历史列表）
# Annotated + add_messages 的作用：每次往 messages 里"追加"，而不是"覆盖"
# 你直接继承它就够了，不需要从零写

class AgentState(MessagesState):
    """
    旅行 Agent 的状态

    目前只需要 messages（消息历史），继承 MessagesState 就自动有了。
    Phase 4 加 RAG 时可以在这里扩展更多字段，比如：
      - user_preferences: str  # 用户偏好
      - retrieved_docs: list   # 检索到的文档
    """
    pass
