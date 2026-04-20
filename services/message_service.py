"""消息保存与消息侧记忆沉淀服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import ChatSession, Message
from db.repositories.message_repository import add_message
from db.repositories.session_event_repository import create_session_event
from domain.plan_option.splitters import strip_markdown_to_text
from services.memory_service import MemoryService
from services.preference_service import PreferenceService


def _truncate_text(text: str | None, max_length: int = 180) -> str:
    """把文本裁剪到适合摘要展示的长度。"""
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1]}…"


def _summarize_message_content(raw_text: str, max_length: int = 90) -> str:
    """把消息内容压缩成适合事件预览的短句。"""
    return _truncate_text(strip_markdown_to_text(raw_text), max_length=max_length)


def _touch_session(
    session: ChatSession,
    *,
    latest_user_message: str | None = None,
) -> None:
    """更新会话的最近活跃信息。"""
    now = datetime.now()
    session.updated_at = now
    session.last_message_at = now
    if latest_user_message is not None:
        session.latest_user_message = latest_user_message


class MessageService:
    """负责用户/助手消息保存，以及由消息触发的记忆沉淀。"""

    def __init__(self, db: Session):
        self.db = db
        self.memory_service = MemoryService(db)
        self.preference_service = PreferenceService(db)

    def save_user_message(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        content: str,
    ) -> Message:
        """保存用户消息并刷新会话活跃时间。"""
        _touch_session(session, latest_user_message=content)
        message = add_message(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=session.active_plan_option_id,
            role="user",
            content=content,
            content_format="text",
        )
        remembered_preferences = self.preference_service.remember_from_message(
            user_id=user_id,
            session_id=session.id,
            message_id=message.id,
            text=content,
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            message_id=message.id,
            plan_option_id=session.active_plan_option_id,
            event_type="user_message_saved",
            event_payload={
                "content_preview": _summarize_message_content(content, 80),
                "remembered_preferences": [
                    f"{item.preference_category}.{item.preference_key}"
                    for item in remembered_preferences
                ],
            },
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self.db.commit()
        self.db.refresh(message)
        self.db.refresh(session)
        return message

    def save_assistant_message(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        content: str,
        tool_outputs: list[str] | None = None,
        has_error: bool = False,
    ) -> Message:
        """保存助手消息。"""
        _touch_session(session)
        metadata = {
            "tool_outputs": tool_outputs or [],
            "has_error": has_error,
        }
        message = add_message(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=session.active_plan_option_id,
            role="assistant",
            content=content,
            content_format="markdown",
            metadata=metadata,
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            message_id=message.id,
            plan_option_id=session.active_plan_option_id,
            event_type="assistant_message_saved",
            event_payload={
                "content_preview": _summarize_message_content(content, 100),
                "has_error": has_error,
                "tool_output_count": len(tool_outputs or []),
            },
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self.db.commit()
        self.db.refresh(message)
        self.db.refresh(session)
        return message
