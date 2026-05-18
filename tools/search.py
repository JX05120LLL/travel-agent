"""
Tavily 网络搜索工具
==================
Tavily 是专门为 LLM 设计的搜索 API，返回的结果比 Google 更"干净"，
已经帮你过滤掉广告和无关内容，适合直接喂给 LLM 使用。

用途：搜索景点介绍、当地美食推荐、旅行攻略等
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import os
from langchain_core.tools import tool
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


def _read_timeout_seconds(default: float = 45.0) -> float:
    raw = os.getenv("TAVILY_TIMEOUT_SECONDS", str(default))
    try:
        value = float(raw or default)
    except (TypeError, ValueError):
        value = default
    return max(value, 1.0)


TAVILY_TIMEOUT_SECONDS = _read_timeout_seconds()


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
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            client.search,
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=True,
        )
        try:
            response = future.result(timeout=TAVILY_TIMEOUT_SECONDS)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    except FutureTimeoutError:
        return (
            "搜索超时：当前联网搜索响应过慢，我先跳过这一步。"
            "如果你愿意，我可以基于已有信息先给你一版不依赖联网搜索的方案。"
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
