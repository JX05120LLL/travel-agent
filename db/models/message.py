"""消息模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSONB,
    Mapped,
    String,
    Text,
    UUID,
    UniqueConstraint,
    datetime,
    func,
    mapped_column,
    relationship,
    text,
    uuid,
)
from db.base import Base


class Message(Base):
    """会话中的单条消息。"""

    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name="chk_messages_role",
        ),
        CheckConstraint(
            "content_format IN ('text', 'markdown', 'json')",
            name="chk_messages_content_format",
        ),
        UniqueConstraint(
            "session_id",
            "sequence_no",
            name="uq_messages_session_sequence",
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="text"
    )
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_call_id: Mapped[str | None] = mapped_column(String(100))
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    message_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    user: Mapped["User | None"] = relationship(back_populates="messages")
    plan_option: Mapped["PlanOption | None"] = relationship(back_populates="messages")
    comparison: Mapped["PlanComparison | None"] = relationship(
        back_populates="messages"
    )
    trip: Mapped["Trip | None"] = relationship(back_populates="messages")
    sourced_preferences: Mapped[list["UserPreference"]] = relationship(
        back_populates="source_message"
    )
    events: Mapped[list["SessionEvent"]] = relationship(back_populates="message")
