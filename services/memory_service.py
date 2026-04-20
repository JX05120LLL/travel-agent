"""会话记忆与运行时上下文服务。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from db.models import (
    ChatSession,
    Message,
    PlanComparison,
    PlanOption,
    UserPreference,
)
from db.repositories.comparison_repository import get_active_comparison
from db.repositories.message_repository import list_messages
from db.repositories.plan_option_repository import (
    get_active_plan_option,
    list_plan_options,
)
from db.repositories.preference_repository import list_active_user_preferences
from domain.plan_option.splitters import build_plan_summary, strip_markdown_to_text
from services.preference_service import PreferenceService

SESSION_RECENT_MESSAGE_LIMIT = 6
SESSION_RECENT_USER_LIMIT = 3
PLAN_RECENT_MESSAGE_LIMIT = 4
USER_PREFERENCE_LIMIT = 8
RUNTIME_CONTEXT_MAX_SECTION_COUNT = 6
RUNTIME_CONTEXT_SECTION_MAX_LENGTH = 900
RUNTIME_CONTEXT_TOTAL_MAX_LENGTH = 3200
RUNTIME_CONTEXT_MIN_REMAINING_LENGTH = 140
RUNTIME_OTHER_PLAN_LIMIT = 3


def _truncate_text(text: str | None, max_length: int = 180) -> str:
    """把文本裁剪到适合摘要展示的长度。"""
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1]}…"


def _summarize_message_content(raw_text: str, max_length: int = 90) -> str:
    """把消息内容压缩成适合记忆上下文的短句。"""
    return _truncate_text(strip_markdown_to_text(raw_text), max_length=max_length)


def _build_preference_display_value(value: dict | None) -> str:
    """把偏好 JSON 压缩成适合注入上下文的一行文本。"""
    if not value:
        return "已记录"
    if "label" in value:
        return str(value["label"])
    if "value" in value:
        return str(value["value"])
    return _truncate_text(str(value), 60)


def _pick_recent_messages(
    messages: list[Message],
    *,
    limit: int = SESSION_RECENT_MESSAGE_LIMIT,
    allowed_roles: tuple[str, ...] = ("user", "assistant", "system"),
) -> list[Message]:
    """挑出最近若干条适合注入上下文的消息。"""
    filtered = [item for item in messages if item.role in allowed_roles]
    if len(filtered) <= limit:
        return filtered
    return filtered[-limit:]


def _build_plan_memory_summary(
    plan_option: PlanOption,
    related_messages: list[Message] | None = None,
) -> str:
    """为候选方案构建一段可注入模型的记忆摘要。"""
    lines = [
        f"方案标题：{plan_option.title}",
        f"方案状态：{plan_option.status}",
    ]

    if plan_option.primary_destination:
        lines.append(f"主目的地：{plan_option.primary_destination}")
    if plan_option.total_days:
        lines.append(f"总天数：{plan_option.total_days} 天")
    if plan_option.travel_start_date or plan_option.travel_end_date:
        lines.append(
            "出行日期："
            f"{plan_option.travel_start_date or '待定'} 至 {plan_option.travel_end_date or '待定'}"
        )

    plan_summary = (plan_option.summary or "").strip()
    if not plan_summary and plan_option.plan_markdown:
        plan_summary = build_plan_summary(plan_option.plan_markdown)
    if plan_summary:
        lines.append(f"当前方案摘要：{_truncate_text(plan_summary, 220)}")

    if related_messages:
        recent_discussions = [
            f"{'用户' if item.role == 'user' else '助手'}：{_summarize_message_content(item.content, 70)}"
            for item in _pick_recent_messages(
                related_messages,
                limit=PLAN_RECENT_MESSAGE_LIMIT,
                allowed_roles=("user", "assistant"),
            )
            if (item.content or "").strip()
        ]
        if recent_discussions:
            lines.append("最近围绕该方案的讨论：")
            lines.extend(f"- {entry}" for entry in recent_discussions)

    return "\n".join(lines)


def _build_session_summary(
    session: ChatSession,
    *,
    recent_messages: list[Message],
    active_plan_option: PlanOption | None,
) -> str:
    """基于最近消息和当前激活方案生成会话摘要。"""
    lines = [f"会话标题：{session.title}"]

    if session.latest_user_message:
        lines.append(
            f"最近一次用户诉求：{_summarize_message_content(session.latest_user_message, 120)}"
        )

    if active_plan_option is not None:
        plan_desc = active_plan_option.title
        if active_plan_option.primary_destination:
            plan_desc += f"（{active_plan_option.primary_destination}）"
        if active_plan_option.total_days:
            plan_desc += f"，{active_plan_option.total_days} 天"
        lines.append(f"当前激活方案：{plan_desc}")

    recent_user_messages = [
        _summarize_message_content(item.content, 80)
        for item in recent_messages
        if item.role == "user" and (item.content or "").strip()
    ][-SESSION_RECENT_USER_LIMIT:]
    if recent_user_messages:
        lines.append("近期用户关注点：")
        lines.extend(f"- {entry}" for entry in recent_user_messages)

    recent_assistant_messages = [
        _summarize_message_content(item.content, 100)
        for item in recent_messages
        if item.role == "assistant" and (item.content or "").strip()
    ][-2:]
    if recent_assistant_messages:
        lines.append("近期助手输出重点：")
        lines.extend(f"- {entry}" for entry in recent_assistant_messages)

    return "\n".join(lines)


def _build_user_preference_summary(preferences: list[UserPreference]) -> str | None:
    """把长期偏好列表压缩成运行时可注入的摘要。"""
    if not preferences:
        return None

    sorted_preferences = sorted(
        preferences,
        key=lambda item: (
            0 if item.source == "user_explicit" else 1,
            -float(item.confidence or 0),
            -(item.updated_at.timestamp() if item.updated_at else 0),
        ),
        reverse=False,
    )[:USER_PREFERENCE_LIMIT]

    explicit_lines: list[str] = []
    inferred_lines: list[str] = []
    for item in sorted_preferences:
        label = _build_preference_display_value(item.preference_value)
        confidence = Decimal(str(item.confidence or 0))
        line = f"- {item.preference_category}.{item.preference_key}：{label}（置信度 {confidence:.2f}）"
        if item.source == "user_explicit" or confidence >= Decimal("0.90"):
            explicit_lines.append(line)
        else:
            inferred_lines.append(line)

    lines: list[str] = []
    if explicit_lines:
        lines.append("优先满足的明确偏好：")
        lines.extend(explicit_lines)
    if inferred_lines:
        lines.append("可优先参考的推断偏好：")
        lines.extend(inferred_lines)
    return "\n".join(lines)


def _build_comparison_summary(comparison: PlanComparison) -> str:
    """为方案比较构建简洁摘要。"""
    comparison_items = list(comparison.items)
    lines = [
        f"比较名称：{comparison.name}",
        f"比较状态：{comparison.status}",
    ]
    option_lines: list[str] = []
    for item in comparison_items:
        option = item.plan_option
        option_lines.append(
            f"- {option.title}（目的地：{option.primary_destination or '待补充'}）"
        )
    if option_lines:
        lines.append("当前纳入比较的方案：")
        lines.extend(option_lines)
    if comparison.summary:
        lines.append(f"比较摘要：{comparison.summary}")
    return "\n".join(lines)


@dataclass(slots=True)
class RuntimeContextSection:
    """运行时上下文 section，带优先级，便于做注入预算裁剪。"""

    priority: int
    content: str


def _format_recall_runtime_line(item: dict) -> str:
    """把历史召回结果压缩成适合运行时注入的一行。"""
    title = _truncate_text(str(item.get("title") or "未命名记录"), 60)
    summary = _truncate_text(str(item.get("summary") or "暂无摘要"), 120)
    reasons = "、".join(item.get("reasons") or [])
    line = f"- {title}：{summary}"
    if reasons:
        line += f"；命中原因：{reasons}"
    return line


def _build_recall_runtime_section(recall_result: dict | None) -> str | None:
    """把召回结果组织成更结构化的运行时上下文。"""
    if not recall_result:
        return None

    grouped_matches = recall_result.get("grouped_matches") or {}
    if not any(grouped_matches.values()):
        return (
            recall_result.get("injection_section")
            or (
                "【本轮历史召回】\n"
                + str(recall_result.get("summary") or "未命中可复用历史，请基于当前输入继续规划。")
            )
        )

    lines = [
        "【本轮历史召回】",
        "以下内容来自跨会话历史，仅在与本轮需求一致时复用；若条件不完全一致，只能作为参考样例。",
    ]

    strong_history = grouped_matches.get("strong_history") or []
    if strong_history:
        lines.append("可优先复用的历史正式行程 / 已成型方案：")
        lines.extend(_format_recall_runtime_line(item) for item in strong_history[:2])

    candidate_options = grouped_matches.get("candidate_options") or []
    if candidate_options:
        lines.append("可借鉴的历史候选方案：")
        lines.extend(_format_recall_runtime_line(item) for item in candidate_options[:3])

    relevant_preferences = grouped_matches.get("relevant_preferences") or []
    if relevant_preferences:
        lines.append("与本轮相关的长期偏好回顾：")
        lines.extend(
            _format_recall_runtime_line(item) for item in relevant_preferences[:3]
        )

    related_sessions = grouped_matches.get("related_sessions") or []
    if related_sessions:
        lines.append("相关历史会话线索：")
        lines.extend(_format_recall_runtime_line(item) for item in related_sessions[:2])

    summary = str(recall_result.get("summary") or "").strip()
    if summary:
        lines.append("召回结论提示：")
        lines.append(_truncate_text(summary, 180))

    return "\n".join(lines)


def _trim_section_content(content: str, *, max_length: int = RUNTIME_CONTEXT_SECTION_MAX_LENGTH) -> str:
    """避免某个 section 过长，把整体上下文预算吃光。"""
    clean = str(content or "").strip()
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1]}…"


def _normalize_section_signature(content: str) -> str:
    """把 section 归一化成稳定签名，用于去重。"""
    normalized_lines = [
        " ".join(str(line).split()).lower()
        for line in str(content or "").splitlines()
        if str(line).strip()
    ]
    return "\n".join(normalized_lines)


def _select_runtime_context_sections(
    *,
    base_sections: list[str],
    sections: list[RuntimeContextSection],
) -> list[str]:
    """按优先级、数量和总字符预算挑选最终注入的 section。"""
    selected_sections: list[str] = []
    seen_signatures: set[str] = set()
    total_length = len("\n\n".join(item for item in base_sections if item))

    for item in sorted(sections, key=lambda current: current.priority):
        if len(selected_sections) >= RUNTIME_CONTEXT_MAX_SECTION_COUNT:
            break

        content = _trim_section_content(item.content)
        if not content:
            continue

        signature = _normalize_section_signature(content)
        if not signature or signature in seen_signatures:
            continue

        separator_length = 2 if (base_sections or selected_sections) else 0
        remaining_length = (
            RUNTIME_CONTEXT_TOTAL_MAX_LENGTH - total_length - separator_length
        )
        if remaining_length <= 0:
            break

        if len(content) > remaining_length:
            if remaining_length < RUNTIME_CONTEXT_MIN_REMAINING_LENGTH:
                break
            content = _trim_section_content(content, max_length=remaining_length)
            signature = _normalize_section_signature(content)
            if not signature or signature in seen_signatures:
                break

        selected_sections.append(content)
        seen_signatures.add(signature)
        total_length += separator_length + len(content)

    return selected_sections


def _collect_runtime_context_sections(
    *,
    context: dict,
    recall_result: dict | None,
    extra_sections: list[str] | None,
) -> list[RuntimeContextSection]:
    """按优先级收集运行时上下文 section，并做数量预算控制。"""
    sections: list[RuntimeContextSection] = []

    if context["active_plan_summary"]:
        sections.append(
            RuntimeContextSection(
                priority=10,
                content=f"【当前激活方案记忆】\n{context['active_plan_summary']}",
            )
        )

    if extra_sections:
        for index, section in enumerate(item for item in extra_sections if item):
            sections.append(
                RuntimeContextSection(
                    priority=20 + index,
                    content=section,
                )
            )

    if context["session_summary"]:
        sections.append(
            RuntimeContextSection(
                priority=40,
                content=f"【当前会话摘要】\n{context['session_summary']}",
            )
        )

    if context["user_preference_summary"]:
        sections.append(
            RuntimeContextSection(
                priority=50,
                content=(
                    "【用户长期偏好】\n"
                    "已结合本轮输入做过冲突治理：若与当前轮明确要求冲突，以当前轮要求为准。\n"
                    f"{context['user_preference_summary']}"
                ),
            )
        )

    recall_section = _build_recall_runtime_section(recall_result)
    if recall_section:
        sections.append(
            RuntimeContextSection(
                priority=60,
                content=recall_section,
            )
        )

    if context["active_comparison_summary"]:
        sections.append(
            RuntimeContextSection(
                priority=70,
                content=f"【当前方案比较状态】\n{context['active_comparison_summary']}",
            )
        )

    other_plans = [
        item
        for item in context["plan_summaries"]
        if item["id"] != context["active_plan_option_id"]
    ]
    if other_plans:
        other_plan_lines = [
            f"- {item['title']}（状态：{item['status']}；目的地：{item['primary_destination'] or '待补充'}）"
            for item in other_plans[:RUNTIME_OTHER_PLAN_LIMIT]
        ]
        sections.append(
            RuntimeContextSection(
                priority=90,
                content=(
                    "【当前工作区内的其他候选方案】\n"
                    "如用户明确要求切换、比较或新建方案，再处理这些其他方案。\n"
                    + "\n".join(other_plan_lines)
                ),
            )
        )

    return sections


def build_langchain_history(messages: list[Message]) -> list:
    """把数据库里的消息转换成 LangChain 消息对象。"""
    history = []
    for item in messages:
        content = (item.content or "").strip()
        if not content:
            continue

        if item.role == "user":
            history.append(HumanMessage(content=content))
        elif item.role == "assistant":
            history.append(AIMessage(content=content))
        elif item.role == "system":
            history.append(SystemMessage(content=content))

    return history


class MemoryService:
    """负责会话摘要刷新、记忆快照组装和运行时上下文构建。"""

    def __init__(self, db: Session):
        self.db = db
        self.preference_service = PreferenceService(db)

    def refresh_session_memory(
        self,
        *,
        session: ChatSession,
        commit: bool = False,
    ) -> ChatSession:
        """刷新会话摘要和当前激活方案记忆。"""
        messages = list_messages(self.db, session_id=session.id)
        recent_messages = _pick_recent_messages(messages)
        active_plan_option = get_active_plan_option(self.db, session=session)

        session.summary = _build_session_summary(
            session,
            recent_messages=recent_messages,
            active_plan_option=active_plan_option,
        )

        if active_plan_option is not None:
            related_messages = [
                item for item in messages if item.plan_option_id == active_plan_option.id
            ]
            active_plan_option.summary = _build_plan_memory_summary(
                active_plan_option,
                related_messages=related_messages,
            )

        if commit:
            self.db.commit()
            self.db.refresh(session)
            if active_plan_option is not None:
                self.db.refresh(active_plan_option)

        return session

    def build_session_context_payload(
        self,
        *,
        session: ChatSession,
        current_user_input: str | None = None,
    ) -> dict:
        """构建当前会话的运行时记忆快照。"""
        messages = list_messages(self.db, session_id=session.id)
        recent_messages = _pick_recent_messages(messages)
        active_plan_option = get_active_plan_option(self.db, session=session)
        active_comparison = get_active_comparison(self.db, session=session)
        preferences = list_active_user_preferences(self.db, user_id=session.user_id)
        preference_context = self.preference_service.build_injection_context(
            preferences=preferences,
            current_input=current_user_input,
            limit=USER_PREFERENCE_LIMIT,
        )
        active_plan_summary = None
        active_comparison_summary = None

        if active_plan_option is not None:
            related_messages = [
                item for item in messages if item.plan_option_id == active_plan_option.id
            ]
            active_plan_summary = _build_plan_memory_summary(
                active_plan_option,
                related_messages=related_messages,
            )

        if active_comparison is not None:
            active_comparison_summary = _build_comparison_summary(active_comparison)

        all_plan_options = list_plan_options(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
        )
        plan_summaries = [
            {
                "id": str(item.id),
                "title": item.title,
                "branch_name": item.branch_name,
                "status": item.status,
                "is_selected": item.is_selected,
                "parent_plan_option_id": (
                    str(item.parent_plan_option_id) if item.parent_plan_option_id else None
                ),
                "branch_root_option_id": (
                    str(item.branch_root_option_id) if item.branch_root_option_id else None
                ),
                "version_no": item.version_no,
                "primary_destination": item.primary_destination,
                "summary": item.summary,
            }
            for item in all_plan_options
        ]

        return {
            "session_id": str(session.id),
            "session_summary": session.summary,
            "active_plan_option_id": str(active_plan_option.id) if active_plan_option else None,
            "active_plan_title": active_plan_option.title if active_plan_option else None,
            "active_plan_summary": active_plan_summary,
            "active_comparison_id": str(active_comparison.id) if active_comparison else None,
            "active_comparison_summary": active_comparison_summary,
            "user_preference_summary": preference_context["summary"],
            "user_preference_context": preference_context,
            "recent_messages": recent_messages,
            "plan_summaries": plan_summaries,
        }

    def build_runtime_context_messages(
        self,
        *,
        session: ChatSession,
        fallback_history: list | None = None,
        extra_sections: list[str] | None = None,
        current_user_input: str | None = None,
        recall_result: dict | None = None,
    ) -> list:
        """按“会话摘要 + 当前方案记忆 + 最近消息”构建模型输入。"""
        context = self.build_session_context_payload(
            session=session,
            current_user_input=current_user_input,
        )
        base_sections = [
            "你正在一个带工作区状态的旅行规划会话里继续回答。",
            "请优先延续当前会话主线和当前激活方案，不要把其他会话的内容当成当前事实。",
        ]
        dynamic_sections = _collect_runtime_context_sections(
            context=context,
            recall_result=recall_result,
            extra_sections=extra_sections,
        )
        context_sections = base_sections + _select_runtime_context_sections(
            base_sections=base_sections,
            sections=dynamic_sections,
        )

        runtime_messages = [SystemMessage(content="\n\n".join(context_sections))]
        recent_history = build_langchain_history(context["recent_messages"])
        if recent_history:
            runtime_messages.extend(recent_history)
        elif fallback_history:
            runtime_messages.extend(fallback_history)

        return runtime_messages
