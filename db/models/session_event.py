"""会话事件模型。"""

from __future__ import annotations

from db.models.common import (
    DateTime,
    ForeignKey,
    JSONB,
    Mapped,
    String,
    UUID,
    Any,
    datetime,
    func,
    mapped_column,
    relationship,
    text,
    uuid,
)
from db.base import Base


class SessionEvent(Base):
    """会话层事件审计记录。"""

    __tablename__ = "session_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    plan_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
    )
    comparison_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_comparisons.id", ondelete="SET NULL"),
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="SET NULL"),
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="events")
    user: Mapped["User | None"] = relationship(back_populates="session_events")
    message: Mapped["Message | None"] = relationship(back_populates="events")
    plan_option: Mapped["PlanOption | None"] = relationship(back_populates="events")
    comparison: Mapped["PlanComparison | None"] = relationship(back_populates="events")
    trip: Mapped["Trip | None"] = relationship(back_populates="events")
