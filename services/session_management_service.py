"""会话管理服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import ChatSession
from db.repositories.message_repository import list_messages
from db.repositories.session_event_repository import create_session_event
from db.repositories.session_repository import (
    add_session,
    get_session,
    list_sessions,
)
from services.errors import ServiceNotFoundError
from services.memory_service import MemoryService


def _build_session_title(user_input: str) -> str:
    """根据用户第一句话生成一个简短会话标题。"""
    clean_text = " ".join(user_input.strip().split())
    if not clean_text:
        return "新对话"
    return clean_text[:24]


class SessionManagementService:
    """负责会话对象本身的管理，不处理聊天工作区动作编排。"""

    def __init__(self, db: Session):
        self.db = db
        self.memory_service = MemoryService(db)

    def create_session(
        self,
        *,
        user_id: uuid.UUID,
        first_message: str = "",
    ) -> ChatSession:
        """创建一个新的聊天会话。"""
        session = ChatSession(
            user_id=user_id,
            title=_build_session_title(first_message),
            status="active",
            latest_user_message=first_message.strip() or None,
            summary="新会话已创建，等待更多旅行需求。",
        )
        add_session(self.db, session)
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            event_type="session_created",
            event_payload={"title": session.title},
        )
        self.db.commit()
        self.db.refresh(session)
        return session

    def list_sessions(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 20,
    ) -> list[ChatSession]:
        """列出当前用户的会话列表。"""
        return list_sessions(self.db, user_id=user_id, limit=limit)

    def get_session_or_raise(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        """按用户范围获取会话。"""
        session = get_session(self.db, session_id=session_id, user_id=user_id)
        if session is None:
            raise ServiceNotFoundError("会话不存在")
        return session

    def list_messages(
        self,
        *,
        session_id: uuid.UUID,
    ):
        """获取会话消息列表。"""
        return list_messages(self.db, session_id=session_id)

    def rename_session(
        self,
        *,
        session: ChatSession,
        title: str,
        commit: bool = True,
    ) -> ChatSession:
        """重命名会话标题。"""
        resolved_title = " ".join((title or "").split()).strip()
        if not resolved_title:
            raise ValueError("会话标题不能为空。")

        session.title = resolved_title[:200]
        session.updated_at = datetime.now()
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
            event_type="session_renamed",
            event_payload={"title": session.title},
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)

        if commit:
            self.db.commit()
            self.db.refresh(session)

        return session

    def set_session_pinned(
        self,
        *,
        session: ChatSession,
        is_pinned: bool,
        commit: bool = True,
    ) -> ChatSession:
        """更新会话置顶状态。"""
        normalized = bool(is_pinned)
        session.is_pinned = normalized
        session.pinned_at = datetime.now() if normalized else None
        session.updated_at = datetime.now()
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
            event_type="session_pinned_changed",
            event_payload={
                "title": session.title,
                "is_pinned": normalized,
            },
        )

        if commit:
            self.db.commit()
            self.db.refresh(session)

        return session

    def archive_session(
        self,
        *,
        session: ChatSession,
        commit: bool = True,
    ) -> ChatSession:
        """归档一个会话。"""
        session.status = "archived"
        session.archived_at = datetime.now()
        session.updated_at = datetime.now()
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
            event_type="session_archived",
            event_payload={"title": session.title},
        )

        if commit:
            self.db.commit()
            self.db.refresh(session)

        return session

    def delete_session(
        self,
        *,
        session: ChatSession,
        commit: bool = True,
    ) -> ChatSession:
        """软删除一个会话，并同步归档其工作区对象。"""
        session.status = "deleted"
        session.active_plan_option_id = None
        session.active_comparison_id = None
        session.updated_at = datetime.now()

        for option in session.plan_options:
            option.status = "deleted"
            option.is_selected = False
            option.archived_at = datetime.now()

        for comparison in session.plan_comparisons:
            comparison.status = "archived"
            comparison.archived_at = datetime.now()

        for trip in session.trips:
            trip.status = "archived"
            trip.archived_at = datetime.now()

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
            event_type="session_deleted",
            event_payload={"title": session.title},
        )

        if commit:
            self.db.commit()
            self.db.refresh(session)

        return session
