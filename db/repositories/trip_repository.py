"""正式行程相关 repository。"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from db.models import Trip, TripDestination, TripItineraryDay


def add_trip(db: Session, trip: Trip) -> Trip:
    """新增正式行程并立即 flush。"""
    db.add(trip)
    db.flush()
    return trip


def add_trip_destination(
    db: Session,
    destination: TripDestination,
) -> TripDestination:
    """新增正式行程目的地。"""
    db.add(destination)
    return destination


def add_trip_itinerary_day(
    db: Session,
    itinerary_day: TripItineraryDay,
) -> TripItineraryDay:
    """新增正式行程每日安排。"""
    db.add(itinerary_day)
    return itinerary_day


def list_session_trips(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[Trip]:
    """查询当前会话沉淀出的正式行程。"""
    stmt: Select[tuple[Trip]] = (
        select(Trip)
        .where(Trip.session_id == session_id)
        .where(Trip.user_id == user_id)
        .where(Trip.status != "archived")
        .order_by(Trip.updated_at.desc(), Trip.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def get_trip(
    db: Session,
    *,
    session_id: uuid.UUID,
    trip_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Trip | None:
    """查询单个正式行程。"""
    stmt: Select[tuple[Trip]] = (
        select(Trip)
        .where(Trip.id == trip_id)
        .where(Trip.user_id == user_id)
        .where(Trip.session_id == session_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_latest_trip_for_plan_option(
    db: Session,
    *,
    session_id: uuid.UUID,
    plan_option_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Trip | None:
    """查询当前会话里某个候选方案最近一次沉淀出的正式行程。"""
    stmt: Select[tuple[Trip]] = (
        select(Trip)
        .where(Trip.session_id == session_id)
        .where(Trip.source_plan_option_id == plan_option_id)
        .where(Trip.user_id == user_id)
        .where(Trip.status != "archived")
        .order_by(Trip.updated_at.desc(), Trip.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_latest_session_trip(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Trip | None:
    """查询当前会话最近一次生成的有效 Trip。"""
    stmt: Select[tuple[Trip]] = (
        select(Trip)
        .where(Trip.session_id == session_id)
        .where(Trip.user_id == user_id)
        .where(Trip.status != "archived")
        .order_by(Trip.updated_at.desc(), Trip.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_user_trips(
    db: Session,
    *,
    user_id: uuid.UUID,
    exclude_session_id: uuid.UUID | None = None,
) -> list[Trip]:
    """查询用户维度下的正式行程，用于历史召回。"""
    stmt: Select[tuple[Trip]] = select(Trip).where(Trip.user_id == user_id)
    if exclude_session_id is not None:
        stmt = stmt.where((Trip.session_id != exclude_session_id) | (Trip.session_id.is_(None)))
    return list(db.execute(stmt).scalars())
