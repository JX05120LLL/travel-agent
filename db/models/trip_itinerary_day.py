"""行程每日安排模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSONB,
    Mapped,
    String,
    Text,
    UUID,
    UniqueConstraint,
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


class TripItineraryDay(Base):
    """正式行程的每日安排。"""

    __tablename__ = "trip_itinerary_days"

    __table_args__ = (
        UniqueConstraint("trip_id", "day_no", name="uq_trip_itinerary_days_day_no"),
        CheckConstraint("day_no > 0", name="chk_trip_itinerary_days_day_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    day_no: Mapped[int] = mapped_column(Integer, nullable=False)
    trip_date: Mapped[date | None] = mapped_column(Date)
    city_name: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    trip: Mapped["Trip"] = relationship(back_populates="itinerary_days")
