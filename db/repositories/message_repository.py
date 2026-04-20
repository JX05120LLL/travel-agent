"""消息相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from db.models import Message


def list_messages(db: Session, *, session_id: uuid.UUID) -> list[Message]:
    """查询会话下的全部消息。"""
    stmt: Select[tuple[Message]] = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_no.asc(), Message.created_at.asc())
    )
    return list(db.execute(stmt).scalars())


def get_latest_assistant_message(
    db: Session,
    *,
    session_id: uuid.UUID,
) -> Message | None:
    """获取会话里最新的一条助手消息。"""
    stmt: Select[tuple[Message]] = (
        select(Message)
        .where(Message.session_id == session_id)
        .where(Message.role == "assistant")
        .order_by(Message.sequence_no.desc(), Message.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_next_sequence_no(db: Session, *, session_id: uuid.UUID) -> int:
    """为一条新消息分配顺序号。"""
    stmt = select(func.max(Message.sequence_no)).where(Message.session_id == session_id)
    max_sequence = db.execute(stmt).scalar_one_or_none()
    return (max_sequence or 0) + 1


def add_message(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID | None,
    plan_option_id: uuid.UUID | None = None,
    comparison_id: uuid.UUID | None = None,
    trip_id: uuid.UUID | None = None,
    role: str,
    content: str,
    content_format: str = "text",
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    metadata: dict | None = None,
) -> Message:
    """新增一条消息并自动处理顺序号。"""
    message = Message(
        session_id=session_id,
        user_id=user_id,
        plan_option_id=plan_option_id,
        comparison_id=comparison_id,
        trip_id=trip_id,
        role=role,
        content=content,
        content_format=content_format,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        sequence_no=get_next_sequence_no(db, session_id=session_id),
        message_metadata=metadata or {},
    )
    db.add(message)
    db.flush()
    return message
