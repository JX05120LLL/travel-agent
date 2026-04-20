"""历史召回相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import HistoryRecallLog


def list_history_recall_logs(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[HistoryRecallLog]:
    """查询历史召回日志。"""
    stmt: Select[tuple[HistoryRecallLog]] = (
        select(HistoryRecallLog)
        .where(HistoryRecallLog.user_id == user_id)
        .order_by(HistoryRecallLog.created_at.desc())
        .limit(limit)
    )
    if session_id is not None:
        stmt = stmt.where(HistoryRecallLog.session_id == session_id)
    return list(db.execute(stmt).scalars())


def add_history_recall_log(db: Session, log: HistoryRecallLog) -> HistoryRecallLog:
    """新增历史召回日志并立即 flush。"""
    db.add(log)
    db.flush()
    return log
