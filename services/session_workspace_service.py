"""会话工作区聚合服务。

设计目标：
1. 给 Web 层一个更稳定的“工作区入口”。
2. 把 memory / events / checkpoints / recalls / preferences 这些
   与会话工作区强相关的能力聚合到同一层。
3. 让 Controller 风格的接口更接近 Java 里常见的 facade/application service。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from db.models import ChatSession, SessionEvent, UserPreference
from services.checkpoint_service import CheckpointService
from services.errors import ServiceNotFoundError
from services.memory_service import MemoryService
from services.plan_option_service import PlanOptionBranchView, PlanOptionService
from services.preference_service import PreferenceService
from services.recall_service import RecallService
from services.session_audit_service import SessionAuditService
from services.session_management_service import SessionManagementService


@dataclass(slots=True)
class SessionMemorySnapshot:
    """会话工作区的记忆快照。"""

    session: ChatSession
    context_payload: dict
    plan_option_views: list[PlanOptionBranchView]


class SessionWorkspaceService:
    """聚合会话工作区查询与记忆相关操作。"""

    def __init__(self, db: Session):
        self.db = db
        self.session_service = SessionManagementService(db)
        self.memory_service = MemoryService(db)
        self.plan_option_service = PlanOptionService(db)
        self.audit_service = SessionAuditService(db)
        self.checkpoint_service = CheckpointService(db)
        self.recall_service = RecallService(db)
        self.preference_service = PreferenceService(db)

    def get_memory_snapshot(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SessionMemorySnapshot:
        """获取当前会话工作区的完整记忆快照。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        context_payload = self.memory_service.build_session_context_payload(session=session)
        _, plan_option_views = self.plan_option_service.list_plan_option_views(
            session_id=session.id,
            user_id=user_id,
        )
        return SessionMemorySnapshot(
            session=session,
            context_payload=context_payload,
            plan_option_views=plan_option_views,
        )

    def list_events(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[SessionEvent]:
        """列出会话事件。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        return self.audit_service.list_events(session_id=session.id, limit=limit)

    def list_checkpoints(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 20,
    ) -> list[SessionEvent]:
        """列出会话检查点。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        return self.checkpoint_service.list_checkpoints(session_id=session.id, limit=limit)

    def create_checkpoint(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        label: str | None = None,
    ) -> SessionEvent:
        """为当前会话创建检查点。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        return self.checkpoint_service.create_checkpoint(session=session, label=label)

    def rewind_checkpoint(
        self,
        *,
        session_id: uuid.UUID,
        checkpoint_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        """把会话回滚到指定检查点。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        checkpoint = self.checkpoint_service.get_checkpoint(
            session_id=session.id,
            checkpoint_id=checkpoint_id,
        )
        if checkpoint is None:
            raise ServiceNotFoundError("检查点不存在")
        return self.checkpoint_service.rewind_to_checkpoint(
            session=session,
            checkpoint=checkpoint,
        )

    def list_recalls(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 20,
    ):
        """列出会话维度的历史召回日志。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        return self.recall_service.list_recall_logs(
            user_id=user_id,
            session_id=session.id,
            limit=limit,
        )

    def list_preferences(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 8,
    ) -> list[UserPreference]:
        """列出用户长期偏好。"""
        return self.preference_service.list_active_preferences(
            user_id=user_id,
            limit=limit,
        )
