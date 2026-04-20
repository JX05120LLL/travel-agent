"""用户偏好相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import UserPreference


def list_active_user_preferences(
    db: Session,
    *,
    user_id: uuid.UUID,
    limit: int | None = 8,
) -> list[UserPreference]:
    """查询当前用户已激活的长期偏好。"""
    stmt: Select[tuple[UserPreference]] = (
        select(UserPreference)
        .where(UserPreference.user_id == user_id)
        .where(UserPreference.is_active.is_(True))
        .order_by(UserPreference.updated_at.desc(), UserPreference.created_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars())


def get_user_preference(
    db: Session,
    *,
    user_id: uuid.UUID,
    category: str,
    key: str,
) -> UserPreference | None:
    """按分类和键查询单条长期偏好。"""
    stmt: Select[tuple[UserPreference]] = (
        select(UserPreference)
        .where(UserPreference.user_id == user_id)
        .where(UserPreference.preference_category == category)
        .where(UserPreference.preference_key == key)
    )
    return db.execute(stmt).scalar_one_or_none()
