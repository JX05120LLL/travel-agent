"""
LangGraph Agent 核心
=====================

这个文件定义了 Agent 的"大脑结构"：
  节点1：llm_node  → 让 LLM 思考，决定下一步
  节点2：tool_node → 执行 LLM 选择的工具
  条件边：LLM 要调工具 → 去 tool_node；否则 → 结束

流程图：
  START
    ↓
  llm_node（LLM 思考）
    ↓
  要调工具吗？ ── 是 ──→ tool_node（执行工具）
      ↓ 否                      ↓
    END              回到 llm_node（整合结果）

注意：工具执行完后会回到 llm_node，让 LLM 整合结果。
这就是"循环"，LangGraph 自动帮你处理，不用手动写两轮。
"""

import os
os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from agent.state import AgentState
from agent.prompts import SYSTEM_PROMPT
from tools.holiday_calendar import resolve_holiday_dates
from tools.amap import (
    amap_city_route_plan,
    amap_geocode,
    amap_plan_spot_routes,
    amap_route_plan,
    amap_search_nearby_food,
    amap_search_poi,
    amap_search_stays,
)
from tools.weather import get_weather
from tools.search import search_travel_info
from tools.rag_retriever import retrieve_local_knowledge
from tools.feishu_sender import send_to_feishu
from tools.wechat_sender import send_to_wechat_work

load_dotenv()

# ── 初始化 LLM ──────────────────────────────────────────────
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0.7,
)

# ── 注册工具 ─────────────────────────────────────────────────
tools = [
    resolve_holiday_dates,
    amap_geocode,
    amap_search_poi,
    amap_search_nearby_food,
    amap_search_stays,
    amap_route_plan,
    amap_city_route_plan,
    amap_plan_spot_routes,
    get_weather,
    search_travel_info,
    retrieve_local_knowledge,
    send_to_feishu,
    send_to_wechat_work,
]
llm_with_tools = llm.bind_tools(tools)


# ── 节点定义 ─────────────────────────────────────────────────

def llm_node(state: AgentState):
    """
    LLM 节点：让 LLM 思考，输出回答或工具调用请求

    - 接收当前 State（消息历史）
    - 如果是第一轮：决定要不要调工具
    - 如果是工具执行完后的第二轮：整合结果，生成最终回答
    - 返回新消息，LangGraph 自动追加到 State.messages
    """
    from datetime import date
    today = date.today().strftime("%Y年%m月%d日")
    system_with_date = SYSTEM_PROMPT + f"\n\n当前日期：{today}"
    messages = [SystemMessage(content=system_with_date)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    # 返回字典，LangGraph 会把 messages 追加到 State 里
    return {"messages": [response]}


# ── 构建图 ───────────────────────────────────────────────────

def build_graph():
    """
    构建 Agent 图

    StateGraph：有状态的图，每个节点共享 AgentState
    ToolNode：LangGraph 内置节点，自动执行 LLM 请求的工具
    tools_condition：内置条件函数，检查 LLM 输出里有没有 tool_calls
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("llm_node", llm_node)
    graph.add_node("tools", ToolNode(tools))  # 注意：必须命名为 "tools"，tools_condition 内置返回这个名字

    # 添加边
    graph.add_edge(START, "llm_node")             # 起点 → LLM节点

    # 条件边：LLM 输出有 tool_calls → 去执行工具；没有 → 结束
    graph.add_conditional_edges(
        "llm_node",
        tools_condition,   # 内置判断函数，检查 response.tool_calls 是否存在
    )

    # 工具执行完 → 回到 LLM节点（让 LLM 整合结果）
    graph.add_edge("tools", "llm_node")

    return graph.compile()


# 编译好的 Agent，供外部调用
agent = build_graph()
