"""方案比较服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import ChatSession, PlanComparison, PlanComparisonItem
from db.repositories.comparison_repository import (
    add_plan_comparison,
    add_plan_comparison_item,
    clear_plan_comparison_items,
    get_active_comparison,
    get_plan_comparison,
    list_plan_comparisons,
)
from db.repositories.session_event_repository import create_session_event
from services.errors import ServiceNotFoundError
from services.plan_option_service import PlanOptionService
from services.session_management_service import SessionManagementService

DEFAULT_COMPARISON_DIMENSIONS = ["综合体验", "行程强度", "目的地差异"]


class ComparisonService:
    """负责方案比较相关的业务编排。"""

    def __init__(self, db: Session):
        self.db = db
        self.session_service = SessionManagementService(db)
        self.plan_option_service = PlanOptionService(db)

    def list_comparisons(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[ChatSession, list[PlanComparison]]:
        """列出当前会话下的方案比较。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        items = list_plan_comparisons(self.db, session_id=session.id, user_id=user_id)
        return session, items

    def get_comparison_or_raise(
        self,
        *,
        session_id: uuid.UUID,
        comparison_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PlanComparison:
        """获取单个方案比较。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        comparison = get_plan_comparison(
            self.db,
            session_id=session.id,
            comparison_id=comparison_id,
            user_id=user_id,
        )
        if comparison is None:
            raise ServiceNotFoundError("方案比较不存在")
        return comparison

    def create_or_update_comparison(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        plan_option_ids: list[uuid.UUID],
        name: str | None = None,
        commit: bool = True,
    ) -> PlanComparison:
        """基于多个候选方案创建或更新比较记录。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        unique_plan_option_ids = list(dict.fromkeys(plan_option_ids))
        plan_options = [
            self.plan_option_service.get_plan_option_or_raise(
                session=session,
                plan_option_id=plan_option_id,
                user_id=user_id,
            )
            for plan_option_id in unique_plan_option_ids
        ]
        if len(plan_options) < 2:
            raise ValueError("至少需要两个候选方案才能发起比较。")

        title = name or f"{session.title} - 方案比较"
        summary = "本轮比较将围绕以下候选方案展开：" + "、".join(
            item.title for item in plan_options
        )

        comparison = get_active_comparison(self.db, session=session)
        if comparison is None:
            comparison = add_plan_comparison(
                self.db,
                PlanComparison(
                    session_id=session.id,
                    user_id=user_id,
                    name=title,
                    status="active",
                    summary=summary,
                    comparison_dimensions=list(DEFAULT_COMPARISON_DIMENSIONS),
                ),
            )
        else:
            comparison.name = title
            comparison.status = "active"
            comparison.summary = summary
            comparison.comparison_dimensions = list(DEFAULT_COMPARISON_DIMENSIONS)
            clear_plan_comparison_items(self.db, comparison=comparison)

        if (
            session.active_plan_option_id is not None
            and session.active_plan_option_id in {item.id for item in plan_options}
        ):
            comparison.recommended_option_id = session.active_plan_option_id

        for index, option in enumerate(plan_options, start=1):
            add_plan_comparison_item(
                self.db,
                PlanComparisonItem(
                    comparison_id=comparison.id,
                    plan_option_id=option.id,
                    sequence_no=index,
                    notes=f"比较候选：{option.title}",
                ),
            )
            if option.status not in ("selected", "archived", "deleted"):
                option.status = "compared"

        session.active_comparison_id = comparison.id
        session.updated_at = datetime.now()
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            comparison_id=comparison.id,
            event_type="comparison_upserted",
            event_payload={
                "comparison_name": comparison.name,
                "plan_option_ids": [str(item.id) for item in plan_options],
                "recommended_option_id": (
                    str(comparison.recommended_option_id)
                    if comparison.recommended_option_id
                    else None
                ),
                "workspace_state": {
                    "active_plan_option_id": (
                        str(session.active_plan_option_id)
                        if session.active_plan_option_id
                        else None
                    ),
                    "active_comparison_id": str(comparison.id),
                    "comparison_status": comparison.status,
                },
            },
        )

        if commit:
            self.db.commit()
            self.db.refresh(comparison)
            self.db.refresh(session)

        return comparison
