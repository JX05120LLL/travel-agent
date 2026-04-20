"""方案比较相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import ChatSession, PlanComparison, PlanComparisonItem


def add_plan_comparison(db: Session, comparison: PlanComparison) -> PlanComparison:
    """新增方案比较并立即 flush。"""
    db.add(comparison)
    db.flush()
    return comparison


def add_plan_comparison_item(
    db: Session,
    item: PlanComparisonItem,
) -> PlanComparisonItem:
    """新增方案比较项。"""
    db.add(item)
    return item


def clear_plan_comparison_items(
    db: Session,
    *,
    comparison: PlanComparison,
) -> None:
    """清空某个比较下已有的比较项。"""
    for item in list(comparison.items):
        db.delete(item)
    db.flush()


def list_plan_comparisons(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[PlanComparison]:
    """查询当前会话的方案比较列表。"""
    stmt: Select[tuple[PlanComparison]] = (
        select(PlanComparison)
        .where(PlanComparison.session_id == session_id)
        .where(PlanComparison.user_id == user_id)
        .order_by(PlanComparison.updated_at.desc(), PlanComparison.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def get_plan_comparison(
    db: Session,
    *,
    session_id: uuid.UUID,
    comparison_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PlanComparison | None:
    """查询单个方案比较。"""
    stmt: Select[tuple[PlanComparison]] = (
        select(PlanComparison)
        .where(PlanComparison.id == comparison_id)
        .where(PlanComparison.session_id == session_id)
        .where(PlanComparison.user_id == user_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_active_comparison(
    db: Session,
    *,
    session: ChatSession,
) -> PlanComparison | None:
    """获取当前会话的激活比较记录。"""
    if session.active_comparison_id is None:
        return None

    stmt: Select[tuple[PlanComparison]] = (
        select(PlanComparison)
        .where(PlanComparison.id == session.active_comparison_id)
        .where(PlanComparison.session_id == session.id)
    )
    return db.execute(stmt).scalar_one_or_none()
