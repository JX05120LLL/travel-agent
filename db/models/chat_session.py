"""会话模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Mapped,
    String,
    Text,
    UUID,
    datetime,
    func,
    mapped_column,
    relationship,
    uuid,
)
from db.base import Base


class ChatSession(Base):
    """单个聊天会话，也是后续的工作区对象。"""

    __tablename__ = "sessions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="chk_sessions_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    active_plan_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="SET NULL"),
    )
    active_comparison_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_comparisons.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新对话")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    summary: Mapped[str | None] = mapped_column(Text)
    latest_user_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.sequence_no",
    )
    plan_options: Mapped[list["PlanOption"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="PlanOption.session_id",
    )
    active_plan_option: Mapped["PlanOption | None"] = relationship(
        foreign_keys=[active_plan_option_id],
        back_populates="sessions_as_active",
        post_update=True,
    )
    plan_comparisons: Mapped[list["PlanComparison"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="PlanComparison.session_id",
    )
    active_comparison: Mapped["PlanComparison | None"] = relationship(
        foreign_keys=[active_comparison_id],
        back_populates="sessions_as_active",
        post_update=True,
    )
    trips: Mapped[list["Trip"]] = relationship(back_populates="session")
    source_preferences: Mapped[list["UserPreference"]] = relationship(
        back_populates="source_session"
    )
    history_recall_logs: Mapped[list["HistoryRecallLog"]] = relationship(
        back_populates="session"
    )
    events: Mapped[list["SessionEvent"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
