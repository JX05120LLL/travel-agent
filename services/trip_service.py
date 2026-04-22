"""正式行程服务。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import (
    ChatSession,
    PlanComparison,
    PlanOption,
    Trip,
    TripDestination,
    TripItineraryDay,
)
from db.repositories.comparison_repository import get_plan_comparison
from db.repositories.plan_option_repository import get_plan_option
from db.repositories.session_event_repository import create_session_event
from db.repositories.trip_repository import (
    add_trip,
    add_trip_destination,
    add_trip_itinerary_day,
    get_trip,
    list_session_trips,
)
from domain.plan_option.splitters import extract_mentioned_destinations
from services.errors import ServiceNotFoundError
from services.session_management_service import SessionManagementService


class TripService:
    """负责正式 Trip 的查询与生成。"""

    def __init__(self, db: Session):
        self.db = db
        self.session_service = SessionManagementService(db)

    def list_trips(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[ChatSession, list[Trip]]:
        """列出当前会话下的正式行程。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        items = list_session_trips(self.db, session_id=session.id, user_id=user_id)
        return session, items

    def get_trip_or_raise(
        self,
        *,
        session_id: uuid.UUID,
        trip_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Trip:
        """获取单个正式行程。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        trip = get_trip(
            self.db,
            session_id=session.id,
            trip_id=trip_id,
            user_id=user_id,
        )
        if trip is None:
            raise ServiceNotFoundError("正式行程不存在")
        return trip

    def create_trip(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        plan_option_id: uuid.UUID | None = None,
        comparison_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> Trip:
        """从当前工作区上下文生成正式行程。"""
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        comparison = None
        if comparison_id is not None:
            comparison = get_plan_comparison(
                self.db,
                session_id=session.id,
                comparison_id=comparison_id,
                user_id=user_id,
            )
            if comparison is None:
                raise ValueError("指定的方案比较不存在")
        elif session.active_comparison_id is not None:
            comparison = get_plan_comparison(
                self.db,
                session_id=session.id,
                comparison_id=session.active_comparison_id,
                user_id=user_id,
            )

        target_plan_id = plan_option_id
        selection_source = "explicit_plan_option" if plan_option_id is not None else None
        if target_plan_id is None and comparison is not None and comparison.recommended_option_id:
            target_plan_id = comparison.recommended_option_id
            selection_source = "comparison_recommended"
        if target_plan_id is None and session.active_plan_option_id is not None:
            target_plan_id = session.active_plan_option_id
            selection_source = "active_session_plan_option"
        if target_plan_id is None:
            raise ValueError("当前没有可沉淀为正式行程的候选方案")

        plan_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=target_plan_id,
            user_id=user_id,
        )
        if plan_option is None:
            raise ValueError("指定的候选方案不存在")

        return self._create_trip_from_plan_option(
            session=session,
            user_id=user_id,
            plan_option=plan_option,
            comparison=comparison,
            selection_source=selection_source or "unknown",
            commit=commit,
        )

    def _create_trip_from_plan_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        plan_option: PlanOption,
        comparison: PlanComparison | None = None,
        selection_source: str = "unknown",
        commit: bool = True,
    ) -> Trip:
        """把候选方案沉淀为正式行程。"""
        trip = add_trip(
            self.db,
            Trip(
                user_id=user_id,
                session_id=session.id,
                source_plan_option_id=plan_option.id,
                selected_from_comparison_id=comparison.id if comparison else None,
                title=plan_option.title,
                status="confirmed",
                primary_destination=plan_option.primary_destination,
                travel_start_date=plan_option.travel_start_date,
                travel_end_date=plan_option.travel_end_date,
                total_days=plan_option.total_days,
                traveler_profile=dict(plan_option.traveler_profile or {}),
                budget_min=plan_option.budget_min,
                budget_max=plan_option.budget_max,
                pace=plan_option.pace,
                preferences=dict(plan_option.preferences or {}),
                constraints=dict(plan_option.constraints or {}),
                summary=plan_option.summary,
                plan_markdown=plan_option.plan_markdown,
                confirmed_at=datetime.now(),
            ),
        )

        plan_option.is_selected = True
        plan_option.status = "selected"
        session.active_plan_option_id = plan_option.id
        if comparison is not None:
            comparison.recommended_option_id = plan_option.id
            comparison.status = "completed"
            session.active_comparison_id = comparison.id

        self._ensure_trip_destinations_from_plan(trip=trip, plan_option=plan_option)
        self.db.flush()
        self._ensure_trip_itinerary_days(trip=trip)

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=plan_option.id,
            comparison_id=comparison.id if comparison else None,
            trip_id=trip.id,
            event_type="trip_created",
            event_payload={
                "title": trip.title,
                "primary_destination": trip.primary_destination,
                "total_days": trip.total_days,
                "selection_source": selection_source,
                "workspace_state": {
                    "active_plan_option_id": (
                        str(session.active_plan_option_id)
                        if session.active_plan_option_id
                        else None
                    ),
                    "active_comparison_id": (
                        str(session.active_comparison_id)
                        if session.active_comparison_id
                        else None
                    ),
                    "comparison_status": comparison.status if comparison else None,
                },
            },
        )

        if commit:
            self.db.commit()
            self.db.refresh(trip)
            self.db.refresh(session)

        return trip

    def _ensure_trip_destinations_from_plan(
        self,
        *,
        trip: Trip,
        plan_option: PlanOption,
    ) -> None:
        """从候选方案同步目的地到正式行程。"""
        source_destinations = list(plan_option.destinations)
        if not source_destinations:
            destination_names = extract_mentioned_destinations(
                plan_option.primary_destination,
                plan_option.title,
                plan_option.plan_markdown,
            )
            for index, name in enumerate(destination_names, start=1):
                add_trip_destination(
                    self.db,
                    TripDestination(
                        trip=trip,
                        sequence_no=index,
                        destination_name=name,
                        notes="自动从候选方案同步",
                    ),
                )
            return

        for item in source_destinations:
            add_trip_destination(
                self.db,
                TripDestination(
                    trip=trip,
                    sequence_no=item.sequence_no,
                    destination_name=item.destination_name,
                    destination_code=item.destination_code,
                    stay_days=item.stay_days,
                    notes=item.notes,
                ),
            )

    def _ensure_trip_itinerary_days(
        self,
        *,
        trip: Trip,
    ) -> None:
        """为正式行程生成最小可用的每日安排占位。"""
        if trip.total_days is None or trip.total_days <= 0:
            return

        destination_names = [item.destination_name for item in trip.destinations] or [
            trip.primary_destination or "目的地待补充"
        ]
        for day_no in range(1, trip.total_days + 1):
            city_name = destination_names[(day_no - 1) % len(destination_names)]
            add_trip_itinerary_day(
                self.db,
                TripItineraryDay(
                    trip=trip,
                    day_no=day_no,
                    city_name=city_name,
                    title=f"第 {day_no} 天安排",
                    summary=f"围绕 {city_name} 继续完善第 {day_no} 天行程。",
                    items=[],
                ),
            )
