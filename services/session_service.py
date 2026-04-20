"""会话编排服务。

这一层负责承接“用户输入进入后，会话状态如何演进”的业务流程：
1. 先调用 IntentRouter 判断动作意图。
2. 再执行最小必要的工作区状态更新。
3. 最后把需要注入给模型的额外上下文返回给 Web 层。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from db.models import ChatSession, PlanComparison, Trip
from db.repositories.plan_option_repository import (
    get_active_plan_option,
    get_plan_option,
    list_plan_options,
)
from db.repositories.session_event_repository import create_session_event
from domain.plan_option.splitters import (
    extract_mentioned_destinations,
    strip_markdown_to_text,
)
from services.comparison_service import ComparisonService
from services.intent_router import IntentRouter, SessionRouteResult
from services.memory_service import MemoryService
from services.plan_option_service import PlanOptionService
from services.recall_service import RecallService
from services.trip_service import TripService


def _truncate_text(text: str | None, max_length: int = 180) -> str:
    """把文本裁剪到适合摘要展示的长度。"""
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1]}…"


@dataclass(slots=True)
class SessionActionResult:
    """一次会话编排执行后的结果。"""

    route: SessionRouteResult
    extra_sections: list[str] = field(default_factory=list)
    clarification_message: str | None = None
    comparison: PlanComparison | None = None
    recall: dict | None = None
    trip: Trip | None = None


class SessionService:
    """会话应用服务。

    更接近 Java 里的 Application Service：
    - 输入：会话对象 + 用户输入
    - 输出：动作结果 + 给上层使用的结构化信息
    - 不关心 HTTP，不直接拼装响应格式
    """

    def __init__(self, db: Session, *, router: IntentRouter | None = None):
        self.db = db
        self.router = router or IntentRouter(db)
        self.memory_service = MemoryService(db)
        self.plan_option_service = PlanOptionService(db)
        self.recall_service = RecallService(db)
        self.comparison_service = ComparisonService(db)
        self.trip_service = TripService(db)

    def route_user_input(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
    ) -> SessionRouteResult:
        """只做会话动作路由，不执行状态修改。"""
        return self.router.route(
            session=session,
            user_id=user_id,
            user_input=user_input,
        )

    def apply_user_input(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
        route_result: SessionRouteResult | None = None,
    ) -> SessionActionResult:
        """执行一次完整的会话动作编排。"""
        route = route_result or self.route_user_input(
            session=session,
            user_id=user_id,
            user_input=user_input,
        )
        active_plan_option = get_active_plan_option(self.db, session=session)

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=active_plan_option.id if active_plan_option else None,
            event_type="intent_routed",
            event_payload=route.to_event_payload(),
        )

        if route.needs_confirmation:
            return SessionActionResult(
                route=route,
                clarification_message=route.clarification_message,
            )

        result = SessionActionResult(route=route)

        if route.action == "switch_to_existing_option":
            self._execute_switch_to_existing_option(
                session=session,
                user_id=user_id,
                result=result,
            )
        elif route.action == "create_new_option":
            self._execute_create_new_option(
                session=session,
                user_id=user_id,
                user_input=user_input,
                result=result,
            )
        elif route.action == "update_current_option" and active_plan_option is not None:
            self._execute_update_current_option(
                session=session,
                user_id=user_id,
                user_input=user_input,
                active_plan_option_id=active_plan_option.id,
                result=result,
            )
        elif route.action == "expand_current_option" and active_plan_option is not None:
            self._execute_expand_current_option(
                session=session,
                user_id=user_id,
                user_input=user_input,
                active_plan_option_id=active_plan_option.id,
                route=route,
                result=result,
            )
        elif route.action == "continue_current_option" and active_plan_option is not None:
            self._execute_continue_current_option(
                session=session,
                user_id=user_id,
                user_input=user_input,
                active_plan_option_id=active_plan_option.id,
                result=result,
            )

        if route.action == "compare_options":
            result.comparison = self._execute_compare_options(
                session=session,
                user_id=user_id,
                result=result,
            )

        if route.action == "recall_history":
            result.recall = self._execute_history_recall(
                session=session,
                user_id=user_id,
                user_input=user_input,
                result=result,
            )

        if route.action == "finalize_trip":
            result.trip = self._execute_finalize_trip(
                session=session,
                user_id=user_id,
                comparison=result.comparison,
                result=result,
            )

        self.memory_service.refresh_session_memory(session=session, commit=False)
        return result

    def _execute_switch_to_existing_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        result: SessionActionResult,
    ) -> None:
        """切换当前激活方案。"""
        target_option_id = result.route.target_plan_option_id
        if target_option_id is None:
            return

        target_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=target_option_id,
            user_id=user_id,
        )
        if target_option is None:
            return

        target_option_view = self.plan_option_service.activate_option(
            session_id=session.id,
            plan_option_id=target_option.id,
            user_id=user_id,
            commit=False,
        )
        target_option = target_option_view.plan_option
        result.extra_sections.append(
            f"【本轮工作区动作】\n已切换到当前候选方案：{target_option.title}。请围绕它继续回答。"
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=target_option.id,
            event_type="intent_switch_executed",
            event_payload={"title": target_option.title},
        )

    def _execute_create_new_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
        result: SessionActionResult,
    ) -> None:
        """根据当前输入新建候选方案。"""
        mentioned_destinations = extract_mentioned_destinations(user_input)
        primary_destination = mentioned_destinations[0] if mentioned_destinations else None
        new_option_view = self.plan_option_service.create_option(
            session_id=session.id,
            user_id=user_id,
            title=(f"{primary_destination} 方案" if primary_destination else None),
            primary_destination=primary_destination,
            summary=_truncate_text(strip_markdown_to_text(user_input), 160),
            plan_markdown=f"## 新需求草案\n{user_input}",
            activate=True,
            commit=False,
        )
        new_option = new_option_view.plan_option
        result.extra_sections.append(
            f"【本轮工作区动作】\n已根据用户新需求创建新的候选方案：{new_option.title}。"
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=new_option.id,
            event_type="intent_new_option_executed",
            event_payload={"title": new_option.title},
        )

    def _execute_update_current_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
        active_plan_option_id: uuid.UUID,
        result: SessionActionResult,
    ) -> None:
        """明确告诉模型：这轮是在当前方案内修改，而不是另起新分支。"""
        active_plan_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=active_plan_option_id,
            user_id=user_id,
        )
        if active_plan_option is None:
            return

        result.extra_sections.append(
            "【本轮工作区动作】\n"
            f"用户正在修改当前候选方案“{active_plan_option.title}”。"
            " 请在当前方案内直接更新内容，优先沿用已有目的地、时长、预算和偏好；"
            " 不要擅自切到别的方案，也不要默认新建分支。"
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=active_plan_option.id,
            event_type="intent_update_executed",
            event_payload={
                "title": active_plan_option.title,
                "content_preview": _truncate_text(
                    strip_markdown_to_text(user_input),
                    100,
                ),
            },
        )

    def _execute_expand_current_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
        active_plan_option_id: uuid.UUID,
        route: SessionRouteResult,
        result: SessionActionResult,
    ) -> None:
        """把新的城市诉求扩展进当前方案。"""
        active_plan_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=active_plan_option_id,
            user_id=user_id,
        )
        if active_plan_option is None:
            return

        new_destinations = route.mentioned_destinations or extract_mentioned_destinations(
            user_input
        )
        expanded_option_view = self.plan_option_service.expand_option_destinations(
            session_id=session.id,
            plan_option_id=active_plan_option.id,
            user_id=user_id,
            destination_names=[active_plan_option.primary_destination or "", *new_destinations],
            planning_mode="multi_city",
            commit=False,
        )
        active_plan_option = expanded_option_view.plan_option
        result.extra_sections.append(
            "【本轮工作区动作】\n"
            "用户希望在当前方案上扩展更多目的地，请按多城市串联方案继续规划。"
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=active_plan_option.id,
            event_type="intent_expand_executed",
            event_payload={"destinations": new_destinations},
        )

    def _execute_continue_current_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
        active_plan_option_id: uuid.UUID,
        result: SessionActionResult,
    ) -> None:
        """承接当前方案继续往下推进。"""
        active_plan_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=active_plan_option_id,
            user_id=user_id,
        )
        if active_plan_option is None:
            return

        result.extra_sections.append(
            "【本轮工作区动作】\n"
            f"用户正在继续当前候选方案“{active_plan_option.title}”。"
            " 请延续当前方案脉络继续细化，不要跳到其他候选方案；"
            " 如果信息不足，优先提出当前方案仍待确认的关键项。"
        )
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=active_plan_option.id,
            event_type="intent_continue_executed",
            event_payload={
                "title": active_plan_option.title,
                "content_preview": _truncate_text(
                    strip_markdown_to_text(user_input),
                    100,
                ),
            },
        )

    def _execute_compare_options(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        result: SessionActionResult,
    ) -> PlanComparison | None:
        """创建或更新当前方案比较。"""
        target_ids = {item for item in result.route.target_plan_option_ids}
        if len(target_ids) < 2:
            return None

        target_options = [
            option
            for option in list_plan_options(self.db, session_id=session.id, user_id=user_id)
            if option.id in target_ids
        ]
        if len(target_options) < 2:
            return None

        comparison = self.comparison_service.create_or_update_comparison(
            session_id=session.id,
            user_id=user_id,
            plan_option_ids=[item.id for item in target_options],
            commit=False,
        )
        result.extra_sections.append(
            "【本轮工作区动作】\n当前需要比较这些候选方案："
            + "、".join(item.title for item in target_options)
            + "。"
        )
        return comparison

    def _execute_history_recall(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
        result: SessionActionResult,
    ) -> dict:
        """附加历史召回结果。"""
        recall_result = self.recall_service.search_history(
            user_id=user_id,
            query_text=user_input,
            session_id=session.id,
        )
        if (
            not recall_result.get("injection_section")
            and recall_result.get("summary")
        ):
            result.extra_sections.append(f"【本轮历史召回】\n{recall_result['summary']}")
        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            event_type="history_recall_attached",
            event_payload={
                "confidence": recall_result.get("confidence"),
                "matched_count": len(recall_result.get("matches") or []),
                "log_id": recall_result.get("log_id"),
            },
        )
        return recall_result

    def _execute_finalize_trip(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        comparison: PlanComparison | None,
        result: SessionActionResult,
    ) -> Trip:
        """把当前工作区状态沉淀成正式 Trip。"""
        created_trip = self.trip_service.create_trip(
            session_id=session.id,
            user_id=user_id,
            comparison_id=(
                comparison.id if comparison is not None else session.active_comparison_id
            ),
            commit=False,
        )
        result.extra_sections.append(
            f"【本轮工作区动作】\n当前候选方案已沉淀为正式行程：{created_trip.title}。"
            "请以正式行程口吻整理并确认结果。"
        )
        return created_trip
