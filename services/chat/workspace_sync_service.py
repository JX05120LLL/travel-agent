"""Shared workspace auto-sync after an assistant turn completes."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from db.repositories.session_event_repository import create_session_event
from services.travel.comparison_service import ComparisonService
from services.core.external_call_guard import external_call_guard
from services.chat.memory_service import MemoryService
from services.travel.plan_option_service import PlanOptionService
from services.travel.trip_service import TripService


def auto_sync_workspace_after_assistant_reply(
    *,
    db: Session,
    session,
    user_id: uuid.UUID,
    session_action,
) -> dict:
    """Auto-sync plan/comparison/trip artifacts after one assistant reply."""
    plan_option_service = PlanOptionService(db)
    comparison_service = ComparisonService(db)
    trip_service = TripService(db)
    memory_service = MemoryService(db)

    synced_plan_option_id = None
    synced_comparison = None
    synced_trip = None
    comparison_candidate_ids: list[uuid.UUID] = []

    if session.active_plan_option_id is not None:
        try:
            synced_view = plan_option_service.sync_option_from_latest_message(
                session_id=session.id,
                plan_option_id=session.active_plan_option_id,
                user_id=user_id,
                activate=True,
                commit=False,
            )
            synced_plan_option_id = synced_view.plan_option.id
            comparison_candidate_ids.append(synced_plan_option_id)
            try:
                created_items = plan_option_service.create_options_from_latest_message(
                    session_id=session.id,
                    user_id=user_id,
                    commit=False,
                )
                comparison_candidate_ids.extend(
                    item.plan_option.id for item in created_items
                )
            except ValueError:
                pass
        except ValueError:
            synced_plan_option_id = session.active_plan_option_id
            if synced_plan_option_id is not None:
                comparison_candidate_ids.append(synced_plan_option_id)
    else:
        try:
            created_items = plan_option_service.create_options_from_latest_message(
                session_id=session.id,
                user_id=user_id,
                commit=False,
            )
            if created_items:
                synced_plan_option_id = created_items[0].plan_option.id
                comparison_candidate_ids.extend(
                    item.plan_option.id for item in created_items
                )
        except ValueError:
            synced_plan_option_id = None

    deduped_comparison_candidate_ids = list(dict.fromkeys(comparison_candidate_ids))
    if len(deduped_comparison_candidate_ids) > 1:
        synced_comparison = comparison_service.create_or_update_comparison(
            session_id=session.id,
            user_id=user_id,
            plan_option_ids=deduped_comparison_candidate_ids,
            commit=False,
        )
        if synced_comparison.recommended_option_id is not None:
            synced_plan_option_id = synced_comparison.recommended_option_id

    if synced_plan_option_id is not None:
        try:
            synced_trip = trip_service.sync_trip_from_plan_option(
                session_id=session.id,
                user_id=user_id,
                plan_option_id=synced_plan_option_id,
                comparison_id=(
                    synced_comparison.id
                    if synced_comparison is not None
                    else session.active_comparison_id
                ),
                commit=False,
            )
        except ValueError:
            synced_trip = None

    context_payload = memory_service.build_session_context_payload(session=session)
    comparison_decision_payload = comparison_service.build_decision_payload(
        synced_comparison
    )
    recommended_plan_option_id = comparison_decision_payload.get(
        "recommended_plan_option_id"
    )
    if recommended_plan_option_id is None and synced_plan_option_id is not None:
        recommended_plan_option_id = str(synced_plan_option_id)

    recommended_plan_title = comparison_decision_payload.get("recommended_plan_title")
    if recommended_plan_title is None:
        recommended_plan_title = context_payload.get("active_plan_title")

    alternate_plan_titles = comparison_decision_payload.get(
        "alternate_plan_titles"
    ) or []
    recommendation_reasons = comparison_decision_payload.get(
        "recommendation_reasons"
    ) or []
    external_governance = {
        "amap": external_call_guard.snapshot("amap"),
        "amap_mcp": external_call_guard.snapshot("amap_mcp"),
        "fliggy_hotel": external_call_guard.snapshot("fliggy_hotel"),
        "railway12306": external_call_guard.snapshot("railway12306"),
    }
    synced_constraints = (
        dict(getattr(synced_trip, "constraints", None) or {})
        if synced_trip is not None
        else {}
    )
    price_confidence_summary = (
        dict(synced_constraints.get("price_confidence_summary") or {})
        if synced_constraints
        else {}
    )
    delivery_payload = (
        dict(synced_constraints.get("delivery_payload") or {})
        if synced_constraints
        else {}
    )
    map_preview = dict(delivery_payload.get("map_preview") or {}) if delivery_payload else {}
    official_booking_notice = None
    booking_notices = delivery_payload.get("booking_notices")
    if isinstance(booking_notices, list):
        for notice in booking_notices:
            if isinstance(notice, dict) and notice.get("notice"):
                official_booking_notice = notice
                break

    create_session_event(
        db,
        session_id=session.id,
        user_id=user_id,
        plan_option_id=synced_plan_option_id,
        comparison_id=synced_comparison.id if synced_comparison is not None else None,
        trip_id=synced_trip.id if synced_trip is not None else None,
        event_type="workspace_auto_synced",
        event_payload={
            "route_action": session_action.route.action,
            "auto_synced_plan": bool(context_payload.get("active_plan_option_id")),
            "auto_compared_options": synced_comparison is not None,
            "auto_synced_trip": synced_trip is not None,
            "comparison_candidate_ids": [
                str(item) for item in deduped_comparison_candidate_ids
            ],
            "recommended_plan_option_id": recommended_plan_option_id,
            "recommended_plan_title": recommended_plan_title,
            "alternate_plan_titles": alternate_plan_titles,
            "recommendation_reasons": recommendation_reasons,
            "active_trip_id": str(synced_trip.id) if synced_trip is not None else None,
            "active_trip_title": synced_trip.title if synced_trip is not None else None,
            "external_governance": external_governance,
            "trip_document_ready": bool(synced_constraints.get("document_markdown")),
            "hotel_price_status": price_confidence_summary.get("hotel_price_status"),
            "rail_ticket_status": price_confidence_summary.get("rail_ticket_status"),
            "official_booking_notice": official_booking_notice,
            "map_preview_status": {
                "provider_mode": map_preview.get("provider_mode"),
                "has_personal_map": bool(map_preview.get("personal_map_url")),
                "degraded_reason": map_preview.get("degraded_reason"),
            },
        },
    )

    return {
        "route_action": session_action.route.action,
        "active_plan_option_id": context_payload.get("active_plan_option_id"),
        "active_plan_summary": context_payload.get("active_plan_summary"),
        "active_comparison_id": context_payload.get("active_comparison_id"),
        "active_comparison_summary": context_payload.get("active_comparison_summary"),
        "recommended_plan_option_id": recommended_plan_option_id,
        "recommended_plan_title": recommended_plan_title,
        "alternate_plan_titles": alternate_plan_titles,
        "recommendation_reasons": recommendation_reasons,
        "active_trip_id": str(synced_trip.id) if synced_trip is not None else None,
        "active_trip_title": synced_trip.title if synced_trip is not None else None,
        "auto_synced_plan": bool(context_payload.get("active_plan_option_id")),
        "auto_compared_options": synced_comparison is not None,
        "auto_synced_trip": synced_trip is not None,
        "external_governance": external_governance,
        "trip_document_ready": bool(synced_constraints.get("document_markdown")),
        "hotel_price_status": price_confidence_summary.get("hotel_price_status"),
        "rail_ticket_status": price_confidence_summary.get("rail_ticket_status"),
        "official_booking_notice": official_booking_notice,
        "map_preview_status": {
            "provider_mode": map_preview.get("provider_mode"),
            "has_personal_map": bool(map_preview.get("personal_map_url")),
            "degraded_reason": map_preview.get("degraded_reason"),
        },
    }
