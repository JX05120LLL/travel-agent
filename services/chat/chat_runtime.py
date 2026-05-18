"""聊天运行时公共能力。"""

from __future__ import annotations

import os

try:
    from langgraph.errors import GraphRecursionError
except Exception:  # pragma: no cover - 测试环境可能没有安装 langgraph
    GraphRecursionError = None  # type: ignore[assignment]

_agent = None


def _read_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """读取整数环境变量，并保证不低于最小值。"""
    raw = os.getenv(name, str(default))
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        value = default
    return max(value, minimum)


AGENT_RECURSION_LIMIT = _read_int_env("AGENT_RECURSION_LIMIT", 16, minimum=1)


def get_agent():
    """延迟加载已经编译好的 LangGraph Agent。"""
    global _agent
    if _agent is None:
        from agent.graph import agent as compiled_agent

        _agent = compiled_agent
    return _agent


def extract_text(message_chunk) -> str:
    """把 LangGraph 流式 chunk 统一提取成纯文本。"""
    raw = getattr(message_chunk, "content", "") or ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(getattr(block, "text", "") or str(block) for block in raw)
    return str(raw)


def is_agent_recursion_error(exc: Exception) -> bool:
    """兼容识别 GraphRecursionError。"""
    if GraphRecursionError is not None and isinstance(exc, GraphRecursionError):
        return True
    return exc.__class__.__name__ == "GraphRecursionError"


def build_agent_guardrail_message(*, reason: str, partial_answer: str = "") -> str:
    """为递归上限或超时场景生成用户可读的兜底提示。"""
    partial = (partial_answer or "").strip()
    suffix = (
        "\n\n## 系统兜底说明\n"
        f"- {reason}\n"
        "- 为避免长时间等待或进入无效循环，我先停止继续自动调用工具。\n"
        "- 你可以继续补充更明确的信息，比如出发地、日期、预算，或者只指定我先收口哪一部分。"
    )
    if partial:
        return partial + suffix
    return (
        "当前这次规划涉及的工具调用较多，我先停止继续自动调用，避免长时间等待或进入无效循环。"
        f"\n\n原因：{reason}\n"
        "你可以继续补充更明确的信息，比如出发地、日期、预算，或者只指定我先收口哪一部分。"
    )
