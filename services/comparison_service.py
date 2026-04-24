"""方案比较服务。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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

        recommendation_reasons: list[str] = []
        if (
            session.active_plan_option_id is not None
            and session.active_plan_option_id in {item.id for item in plan_options}
        ):
            comparison.recommended_option_id = session.active_plan_option_id
            active_option = next(
                (item for item in plan_options if item.id == session.active_plan_option_id),
                None,
            )
            if active_option is not None:
                recommendation_reasons = [
                    f"当前会话正在围绕「{active_option.title}」继续细化",
                    "该方案与当前工作区上下文保持一致",
                ]
        else:
            recommended_option, recommendation_reasons = self._pick_recommended_option(
                plan_options
            )
            comparison.recommended_option_id = recommended_option.id

        comparison.summary = self._build_comparison_summary_text(
            plan_options=plan_options,
            recommended_option_id=comparison.recommended_option_id,
            recommendation_reasons=recommendation_reasons,
        )

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
                "recommendation_reasons": recommendation_reasons,
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

    @classmethod
    def _pick_recommended_option(
        cls,
        plan_options: list[Any],
    ) -> tuple[Any, list[str]]:
        scored_options = [
            (option, cls._score_plan_option(option))
            for option in plan_options
        ]
        scored_options.sort(
            key=lambda item: (
                item[1]["score"],
                len(str(getattr(item[0], "summary", "") or "")),
                len(str(getattr(item[0], "plan_markdown", "") or "")),
            ),
            reverse=True,
        )
        recommended_option, winning_score = scored_options[0]
        fallback_reason = f"「{recommended_option.title}」的信息完整度更高"
        reasons = winning_score["reasons"][:3] or [fallback_reason]
        return recommended_option, reasons

    @classmethod
    def _score_plan_option(
        cls,
        option: Any,
    ) -> dict[str, Any]:
        score = 0.0
        reasons: list[str] = []

        summary_text = str(getattr(option, "summary", "") or "")
        markdown_text = str(getattr(option, "plan_markdown", "") or "")
        if summary_text:
            score += min(len(summary_text) / 80.0, 2.0)
        if markdown_text:
            score += min(len(markdown_text) / 200.0, 2.0)

        if getattr(option, "primary_destination", None):
            score += 1.0
        if getattr(option, "total_days", None):
            score += 1.0
            reasons.append("行程天数和目的地边界更明确")
        if getattr(option, "pace", None):
            score += 0.5
        if getattr(option, "budget_min", None) is not None or getattr(option, "budget_max", None) is not None:
            score += 0.5

        constraints = dict(getattr(option, "constraints", None) or {})
        structured_context = dict(constraints.get("structured_context") or {})
        amap_context = dict(structured_context.get("amap") or {})
        hotel_context = dict(structured_context.get("hotel_accommodation") or {})
        railway_context = dict(structured_context.get("railway12306") or {})
        assistant_context = dict(structured_context.get("assistant_plan") or {})
        cards = [card for card in amap_context.get("cards") or [] if isinstance(card, dict)]
        routes = [route for route in amap_context.get("routes") or [] if isinstance(route, dict)]
        hotel_cards = [card for card in hotel_context.get("cards") or [] if isinstance(card, dict)]
        railway_cards = [card for card in railway_context.get("cards") or [] if isinstance(card, dict)]
        assistant_cards = [card for card in assistant_context.get("cards") or [] if isinstance(card, dict)]
        card_types = {str(card.get("type") or "") for card in cards}
        hotel_card_types = {str(card.get("type") or "") for card in hotel_cards}
        railway_card_types = {str(card.get("type") or "") for card in railway_cards}
        assistant_card_types = {str(card.get("type") or "") for card in assistant_cards}

        score += min((len(cards) + len(hotel_cards) + len(railway_cards) + len(assistant_cards)) * 0.5, 3.6)
        score += min(len(routes) * 0.8, 2.4)

        if cards or hotel_cards or railway_cards or assistant_cards:
            reasons.append("地图结构化结果更完整")
        if "stay_recommendations" in card_types or "stay_recommendations" in hotel_card_types:
            score += 0.8
            reasons.append("已包含住宿推荐")
        if "food_recommendations" in card_types:
            score += 0.8
            reasons.append("已包含美食推荐")
        if "arrival_recommendation" in railway_card_types:
            score += 0.8
            reasons.append("已包含跨城到达建议")
        if "budget_summary" in assistant_card_types:
            score += 0.6
            reasons.append("已包含预算汇总")
        if "route" in card_types or "spot_route" in card_types:
            score += 1.0
            reasons.append("景点路线信息更完整")
        if any((route.get("legs") or []) for route in routes):
            score += 1.2
            reasons.append("已包含景点间逐段交通")

        deduped_reasons: list[str] = []
        for reason in reasons:
            if reason not in deduped_reasons:
                deduped_reasons.append(reason)

        return {
            "score": score,
            "reasons": deduped_reasons,
        }

    @classmethod
    def _build_comparison_summary_text(
        cls,
        *,
        plan_options: list[Any],
        recommended_option_id: uuid.UUID | None,
        recommendation_reasons: list[str],
    ) -> str:
        recommended_option = next(
            (item for item in plan_options if item.id == recommended_option_id),
            None,
        )
        option_titles = "、".join(item.title for item in plan_options)
        lines = [f"系统已自动比较 {len(plan_options)} 个候选方案：{option_titles}。"]
        if recommended_option is not None:
            lines.append(f"当前推荐方案：{recommended_option.title}。")
        if recommendation_reasons:
            lines.append("推荐理由：" + "；".join(recommendation_reasons[:3]) + "。")

        alternate_titles = [
            item.title for item in plan_options if item.id != recommended_option_id
        ]
        if alternate_titles:
            lines.append("备选方案：" + "、".join(alternate_titles) + "。")
        return "\n".join(lines)

    @classmethod
    def _extract_recommendation_reasons(
        cls,
        summary_text: str | None,
    ) -> list[str]:
        summary_text = str(summary_text or "")
        for line in summary_text.splitlines():
            clean_line = line.strip()
            if clean_line.startswith("推荐理由："):
                raw_reasons = clean_line.replace("推荐理由：", "", 1).strip("。")
                return [part.strip() for part in raw_reasons.split("；") if part.strip()]
        return []

    @classmethod
    def build_decision_payload(
        cls,
        comparison: PlanComparison | None,
    ) -> dict[str, Any]:
        if comparison is None:
            return {
                "recommended_plan_option_id": None,
                "recommended_plan_title": None,
                "alternate_plan_titles": [],
                "recommendation_reasons": [],
            }

        comparison_items = list(getattr(comparison, "items", []) or [])
        recommended_option = getattr(comparison, "recommended_option", None)
        recommended_option_id = (
            str(comparison.recommended_option_id)
            if getattr(comparison, "recommended_option_id", None)
            else None
        )
        recommended_title = getattr(recommended_option, "title", None)
        if recommended_title is None and recommended_option_id is not None:
            for item in comparison_items:
                option = getattr(item, "plan_option", None)
                if option is not None and str(getattr(option, "id", "")) == recommended_option_id:
                    recommended_title = getattr(option, "title", None)
                    break

        alternate_titles: list[str] = []
        for item in comparison_items:
            option = getattr(item, "plan_option", None)
            if option is None:
                continue
            if recommended_option_id is not None and str(getattr(option, "id", "")) == recommended_option_id:
                continue
            title = getattr(option, "title", None)
            if title:
                alternate_titles.append(title)

        return {
            "recommended_plan_option_id": recommended_option_id,
            "recommended_plan_title": recommended_title,
            "alternate_plan_titles": alternate_titles,
            "recommendation_reasons": cls._extract_recommendation_reasons(
                getattr(comparison, "summary", None)
            ),
        }
