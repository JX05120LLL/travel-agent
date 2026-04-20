"""候选方案相关 repository。

约定：
1. 这里只做持久化读写，不做业务编排。
2. 与“方案分支化”有关的计数、插入动作，也放在这里统一承接。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from db.models import ChatSession, PlanOption, PlanOptionDestination


def add_plan_option(db: Session, plan_option: PlanOption) -> PlanOption:
    """新增一个候选方案并立刻 flush，方便上层继续串联后续动作。"""
    db.add(plan_option)
    db.flush()
    return plan_option


def add_plan_option_destination(
    db: Session,
    destination: PlanOptionDestination,
) -> PlanOptionDestination:
    """新增候选方案目的地明细。"""
    db.add(destination)
    db.flush()
    return destination


def count_session_plan_options(
    db: Session,
    *,
    session_id: uuid.UUID,
) -> int:
    """统计当前会话下已有多少个候选方案。"""
    stmt = select(func.count(PlanOption.id)).where(PlanOption.session_id == session_id)
    return int(db.execute(stmt).scalar_one() or 0)


def count_child_plan_options(
    db: Session,
    *,
    parent_plan_option_id: uuid.UUID,
) -> int:
    """统计某个方案已经派生出多少个直接子分支。"""
    stmt = select(func.count(PlanOption.id)).where(
        PlanOption.parent_plan_option_id == parent_plan_option_id
    )
    return int(db.execute(stmt).scalar_one() or 0)


def list_plan_options(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[PlanOption]:
    """查询当前会话下的候选方案列表。"""
    stmt: Select[tuple[PlanOption]] = (
        select(PlanOption)
        .where(PlanOption.session_id == session_id)
        .where(PlanOption.user_id == user_id)
        .where(PlanOption.status != "deleted")
        .order_by(PlanOption.updated_at.desc(), PlanOption.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def get_plan_option(
    db: Session,
    *,
    session_id: uuid.UUID,
    plan_option_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PlanOption | None:
    """查询单个候选方案。"""
    stmt: Select[tuple[PlanOption]] = (
        select(PlanOption)
        .where(PlanOption.id == plan_option_id)
        .where(PlanOption.session_id == session_id)
        .where(PlanOption.user_id == user_id)
        .where(PlanOption.status != "deleted")
    )
    return db.execute(stmt).scalar_one_or_none()


def get_active_plan_option(db: Session, *, session: ChatSession) -> PlanOption | None:
    """获取当前会话的激活方案。"""
    if session.active_plan_option_id is None:
        return None

    stmt: Select[tuple[PlanOption]] = (
        select(PlanOption)
        .where(PlanOption.id == session.active_plan_option_id)
        .where(PlanOption.session_id == session.id)
        .where(PlanOption.status != "deleted")
    )
    return db.execute(stmt).scalar_one_or_none()


def list_user_plan_options_for_recall(
    db: Session,
    *,
    user_id: uuid.UUID,
    exclude_session_id: uuid.UUID | None = None,
) -> list[PlanOption]:
    """查询用户维度下可参与历史召回的候选方案。"""
    stmt: Select[tuple[PlanOption]] = (
        select(PlanOption)
        .where(PlanOption.user_id == user_id)
        .where(PlanOption.status != "deleted")
    )
    if exclude_session_id is not None:
        stmt = stmt.where(PlanOption.session_id != exclude_session_id)
    return list(db.execute(stmt).scalars())
