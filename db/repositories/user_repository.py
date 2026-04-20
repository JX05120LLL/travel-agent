"""用户相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import User


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    """按 ID 查询用户。"""
    stmt: Select[tuple[User]] = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_username(db: Session, username: str) -> User | None:
    """按用户名查询用户。"""
    stmt: Select[tuple[User]] = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def add_user(db: Session, user: User) -> User:
    """新增用户并立即 flush。"""
    db.add(user)
    db.flush()
    return user
