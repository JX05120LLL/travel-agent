"""方案比较模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSONB,
    Mapped,
    String,
    Text,
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


class PlanComparison(Base):
    """多个候选方案之间的比较记录。"""

    __tablename__ = "plan_comparisons"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'archived')",
            name="chk_plan_comparisons_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="方案比较")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    summary: Mapped[str | None] = mapped_column(Text)
    comparison_dimensions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    recommended_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
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
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped["ChatSession"] = relationship(
        back_populates="plan_comparisons", foreign_keys=[session_id]
    )
    user: Mapped["User"] = relationship(back_populates="plan_comparisons")
    recommended_option: Mapped["PlanOption | None"] = relationship(
        back_populates="recommended_in_comparisons",
        foreign_keys=[recommended_option_id],
    )
    items: Mapped[list["PlanComparisonItem"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
        order_by="PlanComparisonItem.sequence_no",
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="comparison")
    selected_trips: Mapped[list["Trip"]] = relationship(
        back_populates="selected_from_comparison",
        foreign_keys="Trip.selected_from_comparison_id",
    )
    sessions_as_active: Mapped[list["ChatSession"]] = relationship(
        back_populates="active_comparison",
        foreign_keys="ChatSession.active_comparison_id",
    )
    events: Mapped[list["SessionEvent"]] = relationship(back_populates="comparison")
