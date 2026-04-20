"""行程目的地模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Text,
    UUID,
    UniqueConstraint,
    datetime,
    func,
    mapped_column,
    relationship,
    uuid,
)
from db.base import Base


class TripDestination(Base):
    """正式行程中的目的地明细。"""

    __tablename__ = "trip_destinations"

    __table_args__ = (
        UniqueConstraint("trip_id", "sequence_no", name="uq_trip_destinations_sequence"),
        CheckConstraint(
            "stay_days IS NULL OR stay_days > 0",
            name="chk_trip_destinations_stay_days",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_name: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_code: Mapped[str | None] = mapped_column(String(50))
    stay_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="destinations")
