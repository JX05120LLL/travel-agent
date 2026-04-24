"""会话相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import ChatSession


def add_session(db: Session, session: ChatSession) -> ChatSession:
    """新增会话并立即 flush。"""
    db.add(session)
    db.flush()
    return session


def list_sessions(
    db: Session,
    *,
    user_id: uuid.UUID,
    limit: int = 20,
) -> list[ChatSession]:
    """按最近消息时间倒序返回用户会话列表。"""
    stmt: Select[tuple[ChatSession]] = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .where(ChatSession.status != "deleted")
        .order_by(
            ChatSession.is_pinned.desc(),
            ChatSession.pinned_at.asc().nulls_last(),
            ChatSession.last_message_at.desc(),
            ChatSession.created_at.desc(),
        )
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def list_user_sessions_for_recall(
    db: Session,
    *,
    user_id: uuid.UUID,
    exclude_session_id: uuid.UUID | None = None,
) -> list[ChatSession]:
    """查询用户维度下可参与历史召回的会话。"""
    stmt: Select[tuple[ChatSession]] = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .where(ChatSession.status != "deleted")
    )
    if exclude_session_id is not None:
        stmt = stmt.where(ChatSession.id != exclude_session_id)
    return list(db.execute(stmt).scalars())


def get_session(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ChatSession | None:
    """按用户范围查询单个会话，避免串会话。"""
    stmt: Select[tuple[ChatSession]] = (
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .where(ChatSession.user_id == user_id)
        .where(ChatSession.status != "deleted")
    )
    return db.execute(stmt).scalar_one_or_none()
