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
from db.repositories.message_repository import get_latest_assistant_message
from db.repositories.plan_option_repository import get_plan_option
from db.repositories.session_event_repository import create_session_event
from db.repositories.trip_repository import (
    add_trip,
    add_trip_destination,
    add_trip_itinerary_day,
    get_latest_session_trip,
    get_trip,
    get_latest_trip_for_plan_option,
    list_session_trips,
)
from domain.plan_option.splitters import extract_mentioned_destinations
from services.errors import ServiceNotFoundError
from services.external_call_guard import external_call_guard
from services.session_management_service import SessionManagementService
from services.structured_travel_service import StructuredTravelService
from services.trip_document_service import TripDocumentService


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

    def sync_trip_from_plan_option(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        plan_option_id: uuid.UUID | None = None,
        comparison_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> Trip:
        """将当前方案自动同步到正式 Trip；已存在则更新，不存在则创建。"""
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
        if target_plan_id is None and comparison is not None and comparison.recommended_option_id:
            target_plan_id = comparison.recommended_option_id
        if target_plan_id is None and session.active_plan_option_id is not None:
            target_plan_id = session.active_plan_option_id
        if target_plan_id is None:
            raise ValueError("当前没有可同步为正式行程的候选方案")

        plan_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=target_plan_id,
            user_id=user_id,
        )
        if plan_option is None:
            raise ValueError("指定的候选方案不存在")

        existing_trip = get_latest_trip_for_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=plan_option.id,
            user_id=user_id,
        )
        if existing_trip is None:
            existing_trip = get_latest_session_trip(
                self.db,
                session_id=session.id,
                user_id=user_id,
            )
        if existing_trip is None:
            return self._create_trip_from_plan_option(
                session=session,
                user_id=user_id,
                plan_option=plan_option,
                comparison=comparison,
                selection_source="auto_sync_create",
                commit=commit,
            )

        return self._update_trip_from_plan_option(
            session=session,
            user_id=user_id,
            trip=existing_trip,
            plan_option=plan_option,
            comparison=comparison,
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
        structured_context = self._ensure_plan_option_structured_context(
            session=session,
            plan_option=plan_option,
        )
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
        self._ensure_trip_itinerary_days(
            trip=trip,
            structured_context=structured_context,
        )
        self._refresh_trip_delivery_payload(trip=trip, structured_context=structured_context)
        constraints = dict(trip.constraints or {})
        price_confidence_summary = dict(constraints.get("price_confidence_summary") or {})

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
                "trip_document_ready": bool(constraints.get("document_markdown")),
                "hotel_price_status": price_confidence_summary.get("hotel_price_status"),
                "rail_ticket_status": price_confidence_summary.get("rail_ticket_status"),
                "external_governance": {
                    "amap": external_call_guard.snapshot("amap"),
                    "fliggy_hotel": external_call_guard.snapshot("fliggy_hotel"),
                    "railway12306": external_call_guard.snapshot("railway12306"),
                },
            },
        )

        if commit:
            self.db.commit()
            self.db.refresh(trip)
            self.db.refresh(session)

        return trip

    def _update_trip_from_plan_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        trip: Trip,
        plan_option: PlanOption,
        comparison: PlanComparison | None = None,
        commit: bool = True,
    ) -> Trip:
        """将既有 Trip 更新为当前方案的最新结构化结果。"""
        structured_context = self._ensure_plan_option_structured_context(
            session=session,
            plan_option=plan_option,
        )

        trip.source_plan_option_id = plan_option.id
        trip.selected_from_comparison_id = comparison.id if comparison else trip.selected_from_comparison_id
        trip.title = plan_option.title
        trip.status = "confirmed"
        trip.primary_destination = plan_option.primary_destination
        trip.travel_start_date = plan_option.travel_start_date
        trip.travel_end_date = plan_option.travel_end_date
        trip.total_days = plan_option.total_days
        trip.traveler_profile = dict(plan_option.traveler_profile or {})
        trip.budget_min = plan_option.budget_min
        trip.budget_max = plan_option.budget_max
        trip.pace = plan_option.pace
        trip.preferences = dict(plan_option.preferences or {})
        trip.constraints = dict(plan_option.constraints or {})
        trip.summary = plan_option.summary
        trip.plan_markdown = plan_option.plan_markdown
        if trip.confirmed_at is None:
            trip.confirmed_at = datetime.now()
        trip.updated_at = datetime.now()

        plan_option.is_selected = True
        plan_option.status = "selected"
        session.active_plan_option_id = plan_option.id
        if comparison is not None:
            comparison.recommended_option_id = plan_option.id
            comparison.status = "completed"
            session.active_comparison_id = comparison.id

        # 先清空旧数据，再按最新方案重建，确保 day/items 与结构化结果一致。
        trip.destinations.clear()
        trip.itinerary_days.clear()
        self.db.flush()

        self._ensure_trip_destinations_from_plan(trip=trip, plan_option=plan_option)
        self.db.flush()
        self._ensure_trip_itinerary_days(
            trip=trip,
            structured_context=structured_context,
        )
        self._refresh_trip_delivery_payload(trip=trip, structured_context=structured_context)
        constraints = dict(trip.constraints or {})
        price_confidence_summary = dict(constraints.get("price_confidence_summary") or {})

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=plan_option.id,
            comparison_id=comparison.id if comparison else None,
            trip_id=trip.id,
            event_type="trip_synced",
            event_payload={
                "title": trip.title,
                "primary_destination": trip.primary_destination,
                "total_days": trip.total_days,
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
                "trip_document_ready": bool(constraints.get("document_markdown")),
                "hotel_price_status": price_confidence_summary.get("hotel_price_status"),
                "rail_ticket_status": price_confidence_summary.get("rail_ticket_status"),
                "external_governance": {
                    "amap": external_call_guard.snapshot("amap"),
                    "fliggy_hotel": external_call_guard.snapshot("fliggy_hotel"),
                    "railway12306": external_call_guard.snapshot("railway12306"),
                },
            },
        )

        if commit:
            self.db.commit()
            self.db.refresh(trip)
            self.db.refresh(session)

        return trip

    def _ensure_plan_option_structured_context(
        self,
        *,
        session: ChatSession,
        plan_option: PlanOption,
    ) -> dict | None:
        constraints = dict(plan_option.constraints or {})
        structured_context = dict(constraints.get("structured_context") or {})
        if any(
            isinstance(section, dict) and section.get("cards")
            for section in structured_context.values()
            if isinstance(section, dict)
        ):
            return structured_context

        latest_assistant = get_latest_assistant_message(self.db, session_id=session.id)
        if latest_assistant is None:
            return structured_context or None

        message_context = StructuredTravelService.build_from_message(latest_assistant)
        if not message_context:
            return structured_context or None

        structured_context.update(message_context)
        constraints["structured_context"] = structured_context
        plan_option.constraints = constraints
        return structured_context

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
        structured_context: dict | None = None,
    ) -> None:
        """为正式行程生成最小可用的每日安排占位。"""
        if trip.total_days is None or trip.total_days <= 0:
            return

        day_payloads = self._build_itinerary_days_payload(
            structured_context=structured_context,
            total_days=trip.total_days,
        )
        destination_names = [item.destination_name for item in trip.destinations] or [
            trip.primary_destination or "目的地待补充"
        ]
        for day_no in range(1, trip.total_days + 1):
            city_name = destination_names[(day_no - 1) % len(destination_names)]
            day_payload = (
                day_payloads[day_no - 1]
                if day_no - 1 < len(day_payloads)
                else {"summary": None, "items": []}
            )
            add_trip_itinerary_day(
                self.db,
                TripItineraryDay(
                    trip=trip,
                    day_no=day_no,
                    city_name=city_name,
                    title=f"第 {day_no} 天安排",
                    summary=day_payload.get("summary")
                    or f"围绕 {city_name} 继续完善第 {day_no} 天行程。",
                    items=day_payload.get("items") or [],
                ),
            )

    def _refresh_trip_delivery_payload(
        self,
        *,
        trip: Trip,
        structured_context: dict | None,
    ) -> None:
        constraints = dict(trip.constraints or {})
        if structured_context:
            constraints["structured_context"] = structured_context

        delivery_payload = TripDocumentService.build_delivery_payload(
            trip=trip,
            structured_context=structured_context,
        )
        constraints["delivery_payload"] = delivery_payload
        constraints["document_markdown"] = TripDocumentService.build_document_markdown(
            delivery_payload
        )
        constraints["price_confidence_summary"] = (
            TripDocumentService.build_price_confidence_summary(delivery_payload)
        )
        trip.constraints = constraints
        if not trip.summary:
            overview = delivery_payload.get("overview") or {}
            trip.summary = overview.get("summary") or trip.summary

    @classmethod
    def _build_itinerary_days_payload(
        cls,
        *,
        structured_context: dict | None,
        total_days: int,
    ) -> list[dict]:
        if total_days <= 0:
            return []

        structured_cards = cls._extract_structured_trip_cards(structured_context)
        transit_items = cls._extract_transit_itinerary_items(structured_context)
        day_items: list[list[dict]] = [[] for _ in range(total_days)]

        spot_sequence_items = [
            dict(item)
            for item in transit_items
            if isinstance(item, dict) and item.get("type") == "spot_sequence"
        ]
        spot_leg_items = [
            dict(item)
            for item in transit_items
            if isinstance(item, dict) and item.get("route_kind") == "spot_leg"
        ]
        other_transit_items = [
            dict(item)
            for item in transit_items
            if isinstance(item, dict)
            and item.get("type") == "transit"
            and item.get("route_kind") != "spot_leg"
        ]

        populated_day_indexes = [0]
        if spot_leg_items:
            leg_chunks = cls._split_items_evenly(spot_leg_items, total_days)
            populated_day_indexes = []
            for day_index, chunk in enumerate(leg_chunks):
                if not chunk:
                    continue
                populated_day_indexes.append(day_index)
                if day_index == 0 and spot_sequence_items:
                    day_items[day_index].extend(spot_sequence_items)
                day_items[day_index].extend(chunk)
        elif spot_sequence_items:
            day_items[0].extend(spot_sequence_items)

        if other_transit_items:
            day_items[0].extend(other_transit_items)

        pinned_day_one_cards: list[dict] = []
        rotating_cards: list[dict] = []
        closing_cards: list[dict] = []
        for card in structured_cards:
            if not isinstance(card, dict):
                continue
            card_copy = dict(card)
            card_type = card_copy.get("type")
            if card_type in {
                "route",
                "spot_route",
                "stay_recommendations",
                "arrival_recommendation",
            }:
                pinned_day_one_cards.append(card_copy)
            elif card_type in {"budget_summary", "travel_notes", "planning_assumptions"}:
                closing_cards.append(card_copy)
            else:
                rotating_cards.append(card_copy)

        if pinned_day_one_cards:
            day_items[0][0:0] = pinned_day_one_cards

        target_day_indexes = populated_day_indexes or [0]
        if not target_day_indexes:
            target_day_indexes = [0]
        for card in rotating_cards:
            target_day = min(
                target_day_indexes,
                key=lambda day_index: (len(day_items[day_index]), day_index),
            )
            day_items[target_day].append(card)

        closing_day_index = (
            max(target_day_indexes)
            if target_day_indexes and len(target_day_indexes) > 1
            else max(total_days - 1, 0)
        )
        for card in closing_cards:
            day_items[closing_day_index].append(card)

        return [
            {
                "summary": cls._build_day_summary(items),
                "items": cls._assign_time_periods(items),
            }
            for items in day_items
        ]

    @staticmethod
    def _split_items_evenly(items: list[dict], bucket_count: int) -> list[list[dict]]:
        if bucket_count <= 0:
            return []
        buckets: list[list[dict]] = [[] for _ in range(bucket_count)]
        if not items:
            return buckets

        active_bucket_count = min(bucket_count, len(items))
        base_size = len(items) // active_bucket_count
        remainder = len(items) % active_bucket_count
        cursor = 0
        for bucket_index in range(active_bucket_count):
            size = base_size + (1 if bucket_index < remainder else 0)
            buckets[bucket_index] = [dict(item) for item in items[cursor : cursor + size]]
            cursor += size
        return buckets

    @staticmethod
    def _build_day_summary(items: list[dict]) -> str | None:
        transit_items = [
            item
            for item in items
            if isinstance(item, dict) and item.get("type") == "transit"
        ]
        spot_sequence = next(
            (
                item
                for item in items
                if isinstance(item, dict) and item.get("type") == "spot_sequence"
            ),
            None,
        )
        if transit_items:
            first = transit_items[0]
            last = transit_items[-1]
            start_name = first.get("from")
            end_name = last.get("to")
            if start_name and end_name:
                return f"当日景点动线：{start_name} -> {end_name}"

        if isinstance(spot_sequence, dict):
            spots = [
                str(name).strip()
                for name in spot_sequence.get("spot_sequence") or []
                if str(name).strip()
            ]
            if len(spots) >= 2:
                return f"当日景点动线：{spots[0]} -> {spots[-1]}"
            if spots:
                return f"当日重点：{spots[0]}"

        first_card = next(
            (
                item
                for item in items
                if isinstance(item, dict)
                and item.get("type")
                in {"route", "spot_route", "poi_list", "arrival_recommendation"}
            ),
            None,
        )
        if isinstance(first_card, dict):
            return first_card.get("summary")
        return None

    @staticmethod
    def _infer_item_time_period(item: dict, index: int) -> str:
        item_type = item.get("type")
        route_kind = item.get("route_kind")
        if item_type in {"spot_sequence", "route", "spot_route"}:
            return "morning"
        if item_type == "arrival_recommendation":
            return "morning"
        if item_type == "stay_recommendations":
            return "evening"
        if item_type == "food_recommendations":
            return "afternoon" if index <= 1 else "evening"
        if item_type == "poi_list":
            return "afternoon"
        if item_type in {"budget_summary", "travel_notes", "planning_assumptions"}:
            return "evening"
        if item_type == "transit":
            if route_kind == "spot_leg":
                period_cycle = ("morning", "afternoon", "evening")
                return period_cycle[min(index, len(period_cycle) - 1)]
            return "morning"
        return "afternoon"

    @classmethod
    def _assign_time_periods(cls, items: list[dict]) -> list[dict]:
        decorated_items: list[dict] = []
        spot_leg_index = 0
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            if item.get("type") == "transit" and item.get("route_kind") == "spot_leg":
                period = cls._infer_item_time_period(item, spot_leg_index)
                spot_leg_index += 1
            else:
                period = cls._infer_item_time_period(item, index)
            item["time_period"] = period
            decorated_items.append(item)
        return decorated_items

    @classmethod
    def _build_itinerary_items_by_day(
        cls,
        *,
        structured_context: dict | None,
        total_days: int,
    ) -> list[list[dict]]:
        day_payloads = cls._build_itinerary_days_payload(
            structured_context=structured_context,
            total_days=total_days,
        )
        return [list(day.get("items") or []) for day in day_payloads]

    @staticmethod
    def _extract_structured_trip_cards(
        structured_context: dict | None,
    ) -> list[dict]:
        if not isinstance(structured_context, dict):
            return []

        allowed_types = {
            "poi_list",
            "route",
            "spot_route",
            "food_recommendations",
            "stay_recommendations",
            "arrival_recommendation",
            "budget_summary",
            "travel_notes",
            "planning_assumptions",
            "recommendation_reasons",
        }
        result: list[dict] = []
        for section in structured_context.values():
            if not isinstance(section, dict):
                continue
            cards = section.get("cards")
            if not isinstance(cards, list):
                continue
            result.extend(
                dict(card)
                for card in cards
                if isinstance(card, dict) and card.get("type") in allowed_types
            )
        return result

    @staticmethod
    def _extract_transit_itinerary_items(
        structured_context: dict | None,
    ) -> list[dict]:
        if not isinstance(structured_context, dict):
            return []
        amap_context = structured_context.get("amap")
        if not isinstance(amap_context, dict):
            return []

        routes = amap_context.get("routes")
        if not isinstance(routes, list):
            return []

        itinerary_items: list[dict] = []
        for route in routes:
            if not isinstance(route, dict):
                continue

            route_kind = route.get("route_kind")
            if route_kind == "spot_sequence":
                itinerary_items.extend(
                    TripService._build_spot_route_itinerary_items(route)
                )
                continue

            steps = route.get("steps")
            if not isinstance(steps, list) or not steps:
                continue
            itinerary_items.append(
                {
                    "type": "transit",
                    "provider": "amap",
                    "route_kind": route_kind,
                    "from": route.get("origin"),
                    "to": route.get("destination"),
                    "mode": route.get("mode"),
                    "city": route.get("city"),
                    "distance_text": route.get("distance_text"),
                    "duration_text": route.get("duration_text"),
                    "ticket_cost_text": route.get("ticket_cost_text"),
                    "walking_distance_text": route.get("walking_distance_text"),
                    "steps": [
                        step.get("instruction")
                        for step in steps
                        if isinstance(step, dict) and step.get("instruction")
                    ],
                    "step_details": [dict(step) for step in steps if isinstance(step, dict)],
                }
            )
        return itinerary_items

    @staticmethod
    def _build_spot_route_itinerary_items(route: dict) -> list[dict]:
        items: list[dict] = []
        spot_sequence = [
            str(name).strip()
            for name in route.get("spot_sequence") or []
            if str(name).strip()
        ]
        if spot_sequence:
            items.append(
                {
                    "type": "spot_sequence",
                    "provider": "amap",
                    "city": route.get("city"),
                    "mode": route.get("mode"),
                    "spot_sequence": spot_sequence,
                    "original_spot_sequence": route.get("original_spot_sequence") or [],
                    "optimization_note": route.get("optimization_note"),
                    "total_distance_text": route.get("total_distance_text"),
                    "total_duration_text": route.get("total_duration_text"),
                }
            )

        for leg in route.get("legs") or []:
            if not isinstance(leg, dict):
                continue
            steps = leg.get("steps") or []
            items.append(
                {
                    "type": "transit",
                    "provider": "amap",
                    "route_kind": "spot_leg",
                    "segment_no": leg.get("segment_no"),
                    "from": leg.get("origin"),
                    "to": leg.get("destination"),
                    "mode": leg.get("mode") or route.get("mode"),
                    "distance_text": leg.get("distance_text"),
                    "duration_text": leg.get("duration_text"),
                    "ticket_cost_text": leg.get("ticket_cost_text"),
                    "walking_distance_text": leg.get("walking_distance_text"),
                    "steps": [
                        step.get("instruction")
                        for step in steps
                        if isinstance(step, dict) and step.get("instruction")
                    ],
                    "step_details": [dict(step) for step in steps if isinstance(step, dict)],
                }
            )
        return items
