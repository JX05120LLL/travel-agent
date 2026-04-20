"""会话审计与事件查看服务。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from db.repositories.session_event_repository import list_session_events


class SessionAuditService:
    """负责查询会话层的审计事件。"""

    def __init__(self, db: Session):
        self.db = db

    def list_events(
        self,
        *,
        session_id: uuid.UUID,
        limit: int = 50,
    ):
        """列出某个会话的审计事件。"""
        return list_session_events(self.db, session_id=session_id, limit=limit)
