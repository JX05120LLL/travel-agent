"""正式行程模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    Date,
    DateTime,
    Decimal,
    ForeignKey,
    Integer,
    JSONB,
    Mapped,
    Numeric,
    String,
    Text,
    UUID,
    Any,
    date,
    datetime,
    func,
    mapped_column,
    relationship,
    text,
    uuid,
)
from db.base import Base


class Trip(Base):
    """确认后的正式行程。"""

    __tablename__ = "trips"

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'booked', 'completed', 'cancelled', 'archived')",
            name="chk_trips_status",
        ),
        CheckConstraint(
            "total_days IS NULL OR total_days > 0",
            name="chk_trips_total_days",
        ),
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="chk_trips_budget_range",
        ),
        CheckConstraint(
            "pace IS NULL OR pace IN ('relaxed', 'balanced', 'dense')",
            name="chk_trips_pace",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    source_plan_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
    )
    selected_from_comparison_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_comparisons.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="未命名行程")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    primary_destination: Mapped[str | None] = mapped_column(String(100))
    travel_start_date: Mapped[date | None] = mapped_column(Date)
    travel_end_date: Mapped[date | None] = mapped_column(Date)
    total_days: Mapped[int | None] = mapped_column(Integer)
    traveler_profile: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pace: Mapped[str | None] = mapped_column(String(20))
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    constraints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    plan_markdown: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="trips")
    session: Mapped["ChatSession | None"] = relationship(back_populates="trips")
    source_plan_option: Mapped["PlanOption | None"] = relationship(
        back_populates="sourced_trips",
        foreign_keys=[source_plan_option_id],
    )
    selected_from_comparison: Mapped["PlanComparison | None"] = relationship(
        back_populates="selected_trips",
        foreign_keys=[selected_from_comparison_id],
    )
    destinations: Mapped[list["TripDestination"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripDestination.sequence_no",
    )
    itinerary_days: Mapped[list["TripItineraryDay"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripItineraryDay.day_no",
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="trip")
    events: Mapped[list["SessionEvent"]] = relationship(back_populates="trip")
