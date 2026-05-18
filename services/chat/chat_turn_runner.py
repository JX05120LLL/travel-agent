"""共享的单轮聊天执行器，供 Web SSE 和 MCP wrapper 复用。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

from db.models import ChatSession, User
from services.chat.chat_runtime import (
    AGENT_RECURSION_LIMIT,
    build_agent_guardrail_message,
    extract_text,
    get_agent,
    is_agent_recursion_error,
)
from services.chat.memory_service import MemoryService
from services.chat.message_service import MessageService
from services.chat.workspace_sync_service import (
    auto_sync_workspace_after_assistant_reply,
)
from services.core.errors import ServiceNotFoundError
from services.session.session_management_service import SessionManagementService
from services.session.session_service import SessionService, looks_like_rail_only_request
from tools.train_12306 import plan_12306_arrival, plan_12306_transfer

RAIL_FIELD_PATTERNS = {
    "origin_city": r"- 出发城市：([^\n]+)",
    "destination_city": r"- 目的城市：([^\n]+)",
    "depart_date": r"- 出发日期：([^\n]+)",
}


def _resolve_rail_depart_date(text: str) -> str:
    """Resolve common Chinese date words for direct rail queries."""
    normalized = text or ""
    today = date.today()
    explicit = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", normalized)
    if explicit:
        year, month, day = (int(part) for part in explicit.groups())
        return date(year, month, day).isoformat()
    month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日?", normalized)
    if month_day:
        month, day = (int(part) for part in month_day.groups())
        return date(today.year, month, day).isoformat()
    if "后天" in normalized:
        return (today + timedelta(days=2)).isoformat()
    if "明天" in normalized:
        return (today + timedelta(days=1)).isoformat()
    if "今天" in normalized:
        return today.isoformat()
    return ""


def _strip_rail_query_noise(text: str) -> str:
    """Remove common request/date words so city extraction stays simple."""
    clean = re.sub(r"\s+", "", text or "")
    replacements = (
        "帮我查一下",
        "帮我查查",
        "帮我查询",
        "帮我看看",
        "帮我看下",
        "帮我",
        "请查一下",
        "查询一下",
        "查一下",
        "查查",
        "查询",
        "查",
        "看看",
        "看下",
        "有没有",
        "今天",
        "明天",
        "后天",
        "火车票",
        "高铁票",
        "动车票",
        "车票",
        "车次",
        "余票",
        "票价",
        "高铁",
        "动车",
        "火车",
        "12306",
        "的",
    )
    for item in replacements:
        clean = clean.replace(item, "")
    clean = re.sub(r"20\d{2}[-年/]\d{1,2}[-月/]\d{1,2}日?", "", clean)
    clean = re.sub(r"\d{1,2}月\d{1,2}日?", "", clean)
    return clean


def _parse_rail_query(text: str) -> dict[str, str] | None:
    """Extract origin, destination, and date for a rail-only query."""
    clean = _strip_rail_query_noise(text)
    match = re.search(r"([\u4e00-\u9fffA-Za-z]{1,12})到([\u4e00-\u9fffA-Za-z]{1,12})", clean)
    if not match:
        return None
    origin_city = match.group(1).strip()
    destination_city = match.group(2).strip()
    if not origin_city or not destination_city or origin_city == destination_city:
        return None
    return {
        "origin_city": origin_city,
        "destination_city": destination_city,
        "depart_date": _resolve_rail_depart_date(text),
    }


def _extract_rail_query_from_text(text: str) -> dict[str, str] | None:
    """Extract the latest rendered 12306 query from message/tool text."""
    payload: dict[str, str] = {}
    for key, pattern in RAIL_FIELD_PATTERNS.items():
        matches = re.findall(pattern, text or "")
        if matches:
            payload[key] = matches[-1].strip()
    if payload.get("origin_city") and payload.get("destination_city"):
        return {
            "origin_city": payload["origin_city"],
            "destination_city": payload["destination_city"],
            "depart_date": payload.get("depart_date", ""),
        }
    return None


def _resolve_previous_rail_query(session: ChatSession) -> dict[str, str] | None:
    """Reuse the latest 12306 route for short follow-ups like '高铁票呢？'."""
    for message in reversed(list(getattr(session, "messages", []) or [])):
        if getattr(message, "role", None) != "assistant":
            continue
        metadata = dict(getattr(message, "message_metadata", None) or {})
        for output in reversed(list(metadata.get("tool_outputs") or [])):
            query = _extract_rail_query_from_text(str(output))
            if query is not None:
                return query
        query = _extract_rail_query_from_text(getattr(message, "content", "") or "")
        if query is not None:
            return query
    return _parse_rail_query(getattr(session, "title", "") or "")


def _prefers_high_speed(text: str) -> bool:
    return any(keyword in (text or "") for keyword in ("高铁", "动车", "高铁票", "动车票"))


def _asks_transfer(text: str) -> bool:
    return any(keyword in (text or "") for keyword in ("中转", "换乘", "转车"))


def _build_tool_output_fallback_message(
    *,
    partial_answer: str,
    tool_outputs: list[str],
    error_message: str,
) -> str:
    """Build a readable degraded reply when final synthesis fails after tools ran."""
    partial = (partial_answer or "").strip()
    sections = []
    if partial:
        sections.append(partial)
    sections.extend(
        [
            "## 已获取的信息",
            "这次工具查询已经返回，但最终攻略整合阶段出现异常。我先把已拿到的可靠结果给你，避免查询结果丢失。",
        ]
    )
    for index, output in enumerate(tool_outputs, start=1):
        content = str(output or "").strip()
        if not content:
            continue
        sections.append(f"### 工具结果 {index}\n{content}")
    sections.append(f"### 降级说明\n- {error_message}")
    return "\n\n".join(sections)


@dataclass(slots=True)
class ChatTurnEvent:
    """一条可被 Web 或 MCP 消费的中间事件。"""

    event: str
    payload: dict
    final_result: "ChatTurnResult | None" = None


@dataclass(slots=True)
class ChatTurnResult:
    """一轮聊天执行完成后的统一结果。"""

    reply: str
    session_id: str
    is_new_session: bool
    status: str
    degraded_reason: str | None
    tool_outputs: list[str]
    workspace_payload: dict | None
    session: ChatSession
    session_action: object


class ChatTurnRunner:
    """执行一轮完整的用户输入处理流程。"""

    def __init__(self, db):
        self.db = db
        self.session_management_service = SessionManagementService(db)
        self.message_service = MessageService(db)
        self.session_service = SessionService(db)
        self.memory_service = MemoryService(db)

    def run_turn(
        self,
        *,
        user: User,
        message: str,
        session_id: uuid.UUID | None = None,
        fallback_history: list | None = None,
    ) -> ChatTurnResult:
        """同步执行一轮聊天，并返回最终结果。"""
        final_result = None
        for item in self.stream_turn(
            user=user,
            message=message,
            session_id=session_id,
            fallback_history=fallback_history,
        ):
            if item.final_result is not None:
                final_result = item.final_result
        if final_result is None:
            raise RuntimeError("聊天执行结束了，但没有得到最终结果。")
        return final_result

    def stream_turn(
        self,
        *,
        user: User,
        message: str,
        session_id: uuid.UUID | None = None,
        fallback_history: list | None = None,
    ) -> Iterator[ChatTurnEvent]:
        """按事件流方式执行一轮聊天。"""
        user_input = (message or "").strip()
        if not user_input:
            raise ValueError("消息不能为空")

        is_new_session = False
        if session_id is not None:
            try:
                session = self.session_management_service.get_session_or_raise(
                    session_id=session_id,
                    user_id=user.id,
                )
            except ServiceNotFoundError:
                raise ValueError("会话不存在或不属于当前用户") from None
        else:
            session = self.session_management_service.create_session(
                user_id=user.id,
                first_message=user_input,
            )
            is_new_session = True

        session_action = self.session_service.apply_user_input(
            session=session,
            user_id=user.id,
            user_input=user_input,
        )
        self.message_service.save_user_message(
            session=session,
            user_id=user.id,
            content=user_input,
        )

        yield ChatTurnEvent(
            "session",
            {
                "session_id": str(session.id),
                "is_new": is_new_session,
                "title": session.title,
            },
        )
        yield ChatTurnEvent("intent", session_action.route.to_intent_payload())

        rail_query = None
        if looks_like_rail_only_request(user_input):
            rail_query = _parse_rail_query(user_input) or _resolve_previous_rail_query(
                session
            )
        if rail_query is not None:
            yield ChatTurnEvent(
                "phase",
                {"value": "tooling", "label": "正在查询12306车次"},
            )
            if _asks_transfer(user_input):
                tool_output = plan_12306_transfer(**rail_query)
            else:
                tool_output = plan_12306_arrival.invoke(
                    {
                        **rail_query,
                        "prefer_high_speed": _prefers_high_speed(user_input),
                    }
                )
            yield ChatTurnEvent("tool", {"content": tool_output})
            yield ChatTurnEvent(
                "phase",
                {"value": "answering", "label": "正在整理车次结果"},
            )
            yield ChatTurnEvent("token", {"content": tool_output})
            self.message_service.save_assistant_message(
                session=session,
                user_id=user.id,
                content=tool_output,
                tool_outputs=[tool_output],
                has_error=False,
            )
            result = ChatTurnResult(
                reply=tool_output,
                session_id=str(session.id),
                is_new_session=is_new_session,
                status="ok",
                degraded_reason=None,
                tool_outputs=[tool_output],
                workspace_payload=None,
                session=session,
                session_action=session_action,
            )
            yield ChatTurnEvent("done", {"status": "ok"}, final_result=result)
            return

        if session_action.clarification_message:
            clarification_message = session_action.clarification_message
            yield ChatTurnEvent(
                "phase",
                {"value": "answering", "label": "正在确认你的意图"},
            )
            yield ChatTurnEvent("token", {"content": clarification_message})
            self.message_service.save_assistant_message(
                session=session,
                user_id=user.id,
                content=clarification_message,
                tool_outputs=[],
                has_error=False,
            )
            result = ChatTurnResult(
                reply=clarification_message,
                session_id=str(session.id),
                is_new_session=is_new_session,
                status="ok",
                degraded_reason=None,
                tool_outputs=[],
                workspace_payload=None,
                session=session,
                session_action=session_action,
            )
            yield ChatTurnEvent("done", {"status": "ok"}, final_result=result)
            return

        input_messages = self.memory_service.build_runtime_context_messages(
            session=session,
            fallback_history=fallback_history or [],
            extra_sections=session_action.extra_sections,
            current_user_input=user_input,
            recall_result=session_action.recall,
        )
        agent = get_agent()
        input_data = {"messages": input_messages}
        has_tool_output = False
        has_answer_token = False
        tool_outputs: list[str] = []
        final_answer = ""
        llm_answer_buffer = ""

        yield ChatTurnEvent(
            "phase",
            {"value": "planning", "label": "正在分析你的需求"},
        )

        try:
            for event in agent.stream(
                input_data,
                {"recursion_limit": AGENT_RECURSION_LIMIT},
                stream_mode="messages",
            ):
                if not isinstance(event, tuple) or len(event) != 2:
                    continue

                message_chunk, metadata = event
                node = metadata.get("langgraph_node", "")
                text = extract_text(message_chunk)

                if node == "tools":
                    llm_answer_buffer = ""
                    if not has_tool_output:
                        has_tool_output = True
                        yield ChatTurnEvent(
                            "phase",
                            {"value": "tooling", "label": "正在调用旅行工具"},
                        )
                    if text:
                        tool_outputs.append(text)
                        yield ChatTurnEvent("tool", {"content": text})
                elif node == "llm_node" and text:
                    llm_answer_buffer += text

            workspace_payload = None
            final_answer = llm_answer_buffer
            if final_answer.strip():
                if not has_answer_token:
                    has_answer_token = True
                    yield ChatTurnEvent(
                        "phase",
                        {"value": "answering", "label": "正在整理最终建议"},
                    )
                yield ChatTurnEvent("token", {"content": final_answer})
                assistant_message = self.message_service.save_assistant_message(
                    session=session,
                    user_id=user.id,
                    content=final_answer,
                    tool_outputs=tool_outputs,
                    has_error=False,
                    commit=False,
                )
                workspace_payload = auto_sync_workspace_after_assistant_reply(
                    db=self.db,
                    session=session,
                    user_id=user.id,
                    session_action=session_action,
                )
                message_metadata = dict(
                    getattr(assistant_message, "message_metadata", None) or {}
                )
                message_metadata["workspace_sync"] = workspace_payload
                assistant_message.message_metadata = message_metadata
                self.db.commit()
                self.db.refresh(session)
                self.db.refresh(assistant_message)
                yield ChatTurnEvent("workspace", workspace_payload)

            result = ChatTurnResult(
                reply=final_answer,
                session_id=str(session.id),
                is_new_session=is_new_session,
                status="ok",
                degraded_reason=None,
                tool_outputs=tool_outputs,
                workspace_payload=workspace_payload,
                session=session,
                session_action=session_action,
            )
            yield ChatTurnEvent("done", {"status": "ok"}, final_result=result)
        except Exception as exc:
            partial_answer = final_answer or llm_answer_buffer
            if is_agent_recursion_error(exc):
                reason = f"工具调用已达到上限 {AGENT_RECURSION_LIMIT} 次。"
                degraded_reason = "recursion_limit"
                guardrail_message = build_agent_guardrail_message(
                    reason=reason,
                    partial_answer=partial_answer,
                )
                if not has_answer_token:
                    yield ChatTurnEvent(
                        "phase",
                        {"value": "answering", "label": "正在收口阶段性结果"},
                    )
                yield ChatTurnEvent("token", {"content": guardrail_message})
                self.message_service.save_assistant_message(
                    session=session,
                    user_id=user.id,
                    content=guardrail_message,
                    tool_outputs=tool_outputs,
                    has_error=True,
                )
                result = ChatTurnResult(
                    reply=guardrail_message,
                    session_id=str(session.id),
                    is_new_session=is_new_session,
                    status="degraded",
                    degraded_reason=degraded_reason,
                    tool_outputs=tool_outputs,
                    workspace_payload=None,
                    session=session,
                    session_action=session_action,
                )
                yield ChatTurnEvent(
                    "done",
                    {"status": "degraded", "reason": degraded_reason},
                    final_result=result,
                )
                return

            error_message = f"请求失败：{exc}"
            if tool_outputs:
                fallback_message = _build_tool_output_fallback_message(
                    partial_answer=partial_answer,
                    tool_outputs=tool_outputs,
                    error_message=error_message,
                )
                stream_delta = fallback_message
                if final_answer and fallback_message.startswith(final_answer):
                    stream_delta = fallback_message[len(final_answer) :]
                elif final_answer.strip() and fallback_message.startswith(
                    final_answer.strip()
                ):
                    stream_delta = fallback_message[len(final_answer.strip()) :]
                if stream_delta:
                    if not has_answer_token:
                        yield ChatTurnEvent(
                            "phase",
                            {"value": "answering", "label": "正在整理已获取结果"},
                        )
                    yield ChatTurnEvent("token", {"content": stream_delta})
                self.message_service.save_assistant_message(
                    session=session,
                    user_id=user.id,
                    content=fallback_message,
                    tool_outputs=tool_outputs,
                    has_error=False,
                    extra_metadata={
                        "degraded_reason": "agent_finalization_failed",
                        "original_error": str(exc)[:500],
                    },
                )
                result = ChatTurnResult(
                    reply=fallback_message,
                    session_id=str(session.id),
                    is_new_session=is_new_session,
                    status="degraded",
                    degraded_reason="agent_finalization_failed",
                    tool_outputs=tool_outputs,
                    workspace_payload=None,
                    session=session,
                    session_action=session_action,
                )
                yield ChatTurnEvent(
                    "done",
                    {
                        "status": "degraded",
                        "reason": "agent_finalization_failed",
                    },
                    final_result=result,
                )
                return

            self.message_service.save_assistant_message(
                session=session,
                user_id=user.id,
                content=final_answer.strip() or error_message,
                tool_outputs=tool_outputs,
                has_error=True,
            )
            raise
