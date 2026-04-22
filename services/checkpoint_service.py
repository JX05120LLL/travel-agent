"""检查点与回滚服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import ChatSession, PlanOption, SessionEvent
from db.repositories.plan_option_repository import list_plan_options
from db.repositories.session_event_repository import (
    create_session_event,
    get_session_checkpoint,
    list_session_checkpoints,
)
from services.memory_service import MemoryService


class CheckpointService:
    """负责创建会话检查点和执行回滚。"""

    def __init__(self, db: Session):
        self.db = db
        self.memory_service = MemoryService(db)

    def list_checkpoints(
        self,
        *,
        session_id: uuid.UUID,
        limit: int = 20,
    ) -> list[SessionEvent]:
        """列出会话下的检查点。"""
        return list_session_checkpoints(self.db, session_id=session_id, limit=limit)

    def get_checkpoint(
        self,
        *,
        session_id: uuid.UUID,
        checkpoint_id: uuid.UUID,
    ) -> SessionEvent | None:
        """获取单个检查点。"""
        return get_session_checkpoint(
            self.db,
            session_id=session_id,
            checkpoint_id=checkpoint_id,
        )

    @staticmethod
    def _build_snapshot_scope() -> dict:
        """显式声明 checkpoint 覆盖的工作区范围，避免回滚语义靠猜。"""
        return {
            "restores_plan_options": True,
            "restores_active_plan_pointer": True,
            "restores_active_comparison_pointer": True,
            "captures_session_summary_seed": True,
            "summary_refresh_mode": "restore_seed_then_refresh_from_messages",
            "does_not_restore_messages": True,
            "does_not_restore_comparison_rows": True,
            "does_not_restore_trip_rows": True,
        }

    def create_checkpoint(
        self,
        *,
        session: ChatSession,
        label: str | None = None,
        commit: bool = True,
    ) -> SessionEvent:
        """为当前会话创建一个最小可用的检查点快照。"""
        plan_snapshots = []
        for item in list_plan_options(self.db, session_id=session.id, user_id=session.user_id):
            plan_snapshots.append(
                {
                    "id": str(item.id),
                    "title": item.title,
                    "status": item.status,
                    "is_selected": item.is_selected,
                    "primary_destination": item.primary_destination,
                    "total_days": item.total_days,
                    "summary": item.summary,
                    "plan_markdown": item.plan_markdown,
                    "version_no": item.version_no,
                    "branch_name": item.branch_name,
                    "parent_plan_option_id": (
                        str(item.parent_plan_option_id) if item.parent_plan_option_id else None
                    ),
                    "branch_root_option_id": (
                        str(item.branch_root_option_id) if item.branch_root_option_id else None
                    ),
                    "source_plan_option_id": (
                        str(item.source_plan_option_id) if item.source_plan_option_id else None
                    ),
                }
            )

        snapshot_scope = self._build_snapshot_scope()
        payload = {
            "label": (label or "").strip() or f"检查点 {datetime.now().strftime('%m-%d %H:%M')}",
            "session_summary": session.summary,
            "active_plan_option_id": (
                str(session.active_plan_option_id) if session.active_plan_option_id else None
            ),
            "active_comparison_id": (
                str(session.active_comparison_id) if session.active_comparison_id else None
            ),
            "plan_snapshots": plan_snapshots,
            "captured_plan_option_count": len(plan_snapshots),
            "snapshot_scope": snapshot_scope,
            "summary_restore_mode": snapshot_scope["summary_refresh_mode"],
        }
        checkpoint = create_session_event(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
            plan_option_id=session.active_plan_option_id,
            comparison_id=session.active_comparison_id,
            event_type="checkpoint_created",
            event_payload=payload,
        )

        if commit:
            self.db.commit()
            self.db.refresh(checkpoint)

        return checkpoint

    def rewind_to_checkpoint(
        self,
        *,
        session: ChatSession,
        checkpoint: SessionEvent,
        commit: bool = True,
    ) -> ChatSession:
        """把当前会话回退到某个检查点的最小可用状态。"""
        payload = checkpoint.event_payload or {}
        plan_snapshots = payload.get("plan_snapshots") or []
        current_options = {
            str(item.id): item
            for item in list_plan_options(self.db, session_id=session.id, user_id=session.user_id)
        }

        for snapshot in plan_snapshots:
            plan_id = snapshot.get("id")
            option = current_options.get(plan_id)
            if option is None:
                option = PlanOption(
                    id=uuid.UUID(plan_id),
                    session_id=session.id,
                    user_id=session.user_id,
                    parent_plan_option_id=(
                        uuid.UUID(snapshot["parent_plan_option_id"])
                        if snapshot.get("parent_plan_option_id")
                        else None
                    ),
                    branch_root_option_id=(
                        uuid.UUID(snapshot["branch_root_option_id"])
                        if snapshot.get("branch_root_option_id")
                        else None
                    ),
                    source_plan_option_id=(
                        uuid.UUID(snapshot["source_plan_option_id"])
                        if snapshot.get("source_plan_option_id")
                        else None
                    ),
                    branch_name=snapshot.get("branch_name"),
                    title=snapshot.get("title") or "恢复方案",
                    status=snapshot.get("status") or "draft",
                    primary_destination=snapshot.get("primary_destination"),
                    total_days=snapshot.get("total_days"),
                    summary=snapshot.get("summary"),
                    plan_markdown=snapshot.get("plan_markdown"),
                    version_no=snapshot.get("version_no") or 1,
                    is_selected=bool(snapshot.get("is_selected")),
                )
                self.db.add(option)
                self.db.flush()
            else:
                option.parent_plan_option_id = (
                    uuid.UUID(snapshot["parent_plan_option_id"])
                    if snapshot.get("parent_plan_option_id")
                    else None
                )
                option.branch_root_option_id = (
                    uuid.UUID(snapshot["branch_root_option_id"])
                    if snapshot.get("branch_root_option_id")
                    else None
                )
                option.source_plan_option_id = (
                    uuid.UUID(snapshot["source_plan_option_id"])
                    if snapshot.get("source_plan_option_id")
                    else None
                )
                option.branch_name = snapshot.get("branch_name")
                option.title = snapshot.get("title") or option.title
                option.status = snapshot.get("status") or option.status
                option.primary_destination = snapshot.get("primary_destination")
                option.total_days = snapshot.get("total_days")
                option.summary = snapshot.get("summary")
                option.plan_markdown = snapshot.get("plan_markdown")
                option.version_no = snapshot.get("version_no") or option.version_no
                option.is_selected = bool(snapshot.get("is_selected"))
                option.archived_at = None if option.status != "archived" else datetime.now()

            if option.branch_root_option_id is None:
                option.branch_root_option_id = option.id
            if not option.branch_name:
                option.branch_name = "main"

        session.summary = payload.get("session_summary")
        session.active_plan_option_id = (
            uuid.UUID(payload["active_plan_option_id"])
            if payload.get("active_plan_option_id")
            else None
        )
        session.active_comparison_id = (
            uuid.UUID(payload["active_comparison_id"])
            if payload.get("active_comparison_id")
            else None
        )
        session.updated_at = datetime.now()

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=session.user_id,
            plan_option_id=session.active_plan_option_id,
            comparison_id=session.active_comparison_id,
            event_type="checkpoint_rewound",
            event_payload={
                "checkpoint_id": str(checkpoint.id),
                "label": payload.get("label"),
                "snapshot_scope": payload.get("snapshot_scope") or self._build_snapshot_scope(),
                "summary_restore_mode": payload.get("summary_restore_mode")
                or "restore_seed_then_refresh_from_messages",
                "restored_plan_option_count": len(plan_snapshots),
                "restored_active_plan_option_id": (
                    str(session.active_plan_option_id) if session.active_plan_option_id else None
                ),
                "restored_active_comparison_id": (
                    str(session.active_comparison_id) if session.active_comparison_id else None
                ),
                "restored_session_summary_seed": payload.get("session_summary"),
                "summary_refresh_applied": True,
            },
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)

        if commit:
            self.db.commit()
            self.db.refresh(session)

        return session
