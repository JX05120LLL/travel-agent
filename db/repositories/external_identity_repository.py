"""Repositories for external identity mappings."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models.external_identity import ExternalIdentity


def get_external_identity(
    db: Session,
    *,
    channel: str,
    external_user_id: str,
) -> ExternalIdentity | None:
    stmt: Select[tuple[ExternalIdentity]] = (
        select(ExternalIdentity)
        .where(ExternalIdentity.channel == channel)
        .where(ExternalIdentity.external_user_id == external_user_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def add_external_identity(db: Session, item: ExternalIdentity) -> ExternalIdentity:
    db.add(item)
    db.flush()
    return item
