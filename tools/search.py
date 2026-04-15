"""
Tavily 网络搜索工具
==================
Tavily 是专门为 LLM 设计的搜索 API，返回的结果比 Google 更"干净"，
已经帮你过滤掉广告和无关内容，适合直接喂给 LLM 使用。

用途：搜索景点介绍、当地美食推荐、旅行攻略等
"""

import os
from langchain_core.tools import tool
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


@tool
def search_travel_info(query: str) -> str:
    """
    搜索旅行相关信息，包括景点介绍、当地美食、旅行攻略、住宿推荐等。
    当用户询问某个地方有什么好玩的、好吃的、值得去的地方，或需要获取旅行攻略时调用。
    参数 query：搜索关键词，如"成都著名景点"、"西安回民街美食"、"北京3天旅行攻略"
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误：未配置 Tavily API Key（TAVILY_API_KEY），请在 .env 文件中添加"

    try:
        client = TavilyClient(api_key=api_key)
        # search_depth="advanced" 会返回更详细的内容
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True  # 让 Tavily 帮你做一次摘要
        )
    except Exception as e:
        return f"搜索失败：{e}"

    # 整理搜索结果
    result = ""

    # Tavily 的 answer 是对所有结果的总结，非常有用
    if response.get("answer"):
        result += f"【搜索摘要】\n{response['answer']}\n\n"

    # 附上具体来源
    if response.get("results"):
        result += "【详细来源】\n"
        for i, item in enumerate(response["results"][:3], 1):
            result += f"{i}. {item['title']}\n"
            result += f"   {item['content'][:200]}...\n\n"

    return result if result else "未找到相关信息"
