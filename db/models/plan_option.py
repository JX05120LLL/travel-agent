"""候选方案模型。"""

from __future__ import annotations

from db.models.common import (
    Boolean,
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


class PlanOption(Base):
    """会话里的候选旅行方案。"""

    __tablename__ = "plan_options"

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'compared', 'selected', 'archived', 'deleted')",
            name="chk_plan_options_status",
        ),
        CheckConstraint(
            "planning_mode IN ('single_city', 'multi_city', 'compare_candidate')",
            name="chk_plan_options_planning_mode",
        ),
        CheckConstraint(
            "total_days IS NULL OR total_days > 0",
            name="chk_plan_options_total_days",
        ),
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="chk_plan_options_budget_range",
        ),
        CheckConstraint(
            "pace IS NULL OR pace IN ('relaxed', 'balanced', 'dense')",
            name="chk_plan_options_pace",
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
    parent_plan_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
    )
    branch_root_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
    )
    source_plan_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
    )
    branch_name: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="未命名方案"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    planning_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="single_city"
    )
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
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
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
        back_populates="plan_options", foreign_keys=[session_id]
    )
    user: Mapped["User"] = relationship(back_populates="plan_options")
    parent_plan_option: Mapped["PlanOption | None"] = relationship(
        remote_side=[id],
        foreign_keys=[parent_plan_option_id],
        back_populates="child_plan_options",
    )
    child_plan_options: Mapped[list["PlanOption"]] = relationship(
        back_populates="parent_plan_option",
        foreign_keys="PlanOption.parent_plan_option_id",
    )
    branch_root_option: Mapped["PlanOption | None"] = relationship(
        remote_side=[id],
        foreign_keys=[branch_root_option_id],
        back_populates="branch_family_options",
    )
    branch_family_options: Mapped[list["PlanOption"]] = relationship(
        back_populates="branch_root_option",
        foreign_keys="PlanOption.branch_root_option_id",
    )
    source_plan_option: Mapped["PlanOption | None"] = relationship(
        foreign_keys=[source_plan_option_id],
        remote_side=[id],
        back_populates="derived_plan_options",
    )
    derived_plan_options: Mapped[list["PlanOption"]] = relationship(
        back_populates="source_plan_option",
        foreign_keys="PlanOption.source_plan_option_id",
    )
    destinations: Mapped[list["PlanOptionDestination"]] = relationship(
        back_populates="plan_option",
        cascade="all, delete-orphan",
        order_by="PlanOptionDestination.sequence_no",
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="plan_option")
    comparison_items: Mapped[list["PlanComparisonItem"]] = relationship(
        back_populates="plan_option"
    )
    recommended_in_comparisons: Mapped[list["PlanComparison"]] = relationship(
        back_populates="recommended_option",
        foreign_keys="PlanComparison.recommended_option_id",
    )
    sourced_trips: Mapped[list["Trip"]] = relationship(
        back_populates="source_plan_option",
        foreign_keys="Trip.source_plan_option_id",
    )
    sessions_as_active: Mapped[list["ChatSession"]] = relationship(
        back_populates="active_plan_option",
        foreign_keys="ChatSession.active_plan_option_id",
    )
    events: Mapped[list["SessionEvent"]] = relationship(back_populates="plan_option")
