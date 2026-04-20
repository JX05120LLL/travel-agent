"""会话事件与检查点相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import SessionEvent


def create_session_event(
    db: Session,
    *,
    session_id: uuid.UUID,
    event_type: str,
    user_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    plan_option_id: uuid.UUID | None = None,
    comparison_id: uuid.UUID | None = None,
    trip_id: uuid.UUID | None = None,
    event_payload: dict | None = None,
) -> SessionEvent:
    """记录会话层事件，方便后续审计和回放。"""
    event = SessionEvent(
        session_id=session_id,
        user_id=user_id,
        message_id=message_id,
        plan_option_id=plan_option_id,
        comparison_id=comparison_id,
        trip_id=trip_id,
        event_type=event_type,
        event_payload=event_payload or {},
    )
    db.add(event)
    db.flush()
    return event


def list_session_events(
    db: Session,
    *,
    session_id: uuid.UUID,
    limit: int = 50,
) -> list[SessionEvent]:
    """查询会话事件审计日志。"""
    stmt: Select[tuple[SessionEvent]] = (
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .order_by(SessionEvent.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def list_session_checkpoints(
    db: Session,
    *,
    session_id: uuid.UUID,
    limit: int = 20,
) -> list[SessionEvent]:
    """查询会话下已创建的检查点。"""
    stmt: Select[tuple[SessionEvent]] = (
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .where(SessionEvent.event_type == "checkpoint_created")
        .order_by(SessionEvent.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def get_session_checkpoint(
    db: Session,
    *,
    session_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
) -> SessionEvent | None:
    """查询单个检查点。"""
    stmt: Select[tuple[SessionEvent]] = (
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id)
        .where(SessionEvent.id == checkpoint_id)
        .where(SessionEvent.event_type == "checkpoint_created")
    )
    return db.execute(stmt).scalar_one_or_none()
