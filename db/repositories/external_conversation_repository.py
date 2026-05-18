"""Repositories for external conversation mappings."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models.external_conversation import ExternalConversation


def get_external_conversation(
    db: Session,
    *,
    channel: str,
    external_user_id: str,
    conversation_id: str,
) -> ExternalConversation | None:
    stmt: Select[tuple[ExternalConversation]] = (
        select(ExternalConversation)
        .where(ExternalConversation.channel == channel)
        .where(ExternalConversation.external_user_id == external_user_id)
        .where(ExternalConversation.conversation_id == conversation_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def add_external_conversation(
    db: Session,
    item: ExternalConversation,
) -> ExternalConversation:
    db.add(item)
    db.flush()
    return item
