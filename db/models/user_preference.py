"""用户偏好模型。"""

from __future__ import annotations

from db.models.common import (
    Boolean,
    CheckConstraint,
    DateTime,
    Decimal,
    ForeignKey,
    JSONB,
    Mapped,
    Numeric,
    String,
    UUID,
    UniqueConstraint,
    Any,
    datetime,
    func,
    mapped_column,
    relationship,
    text,
    uuid,
)
from db.base import Base


class UserPreference(Base):
    """长期可复用的用户偏好记忆。"""

    __tablename__ = "user_preferences"

    __table_args__ = (
        CheckConstraint(
            "source IN ('user_explicit', 'derived', 'imported', 'system')",
            name="chk_user_preferences_source",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="chk_user_preferences_confidence",
        ),
        UniqueConstraint(
            "user_id",
            "preference_category",
            "preference_key",
            name="uq_user_preferences_user_category_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    preference_category: Mapped[str] = mapped_column(String(50), nullable=False)
    preference_key: Mapped[str] = mapped_column(String(100), nullable=False)
    preference_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="derived")
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("0.7000"),
        server_default=text("0.7000"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="preferences")
    source_session: Mapped["ChatSession | None"] = relationship(
        back_populates="source_preferences"
    )
    source_message: Mapped["Message | None"] = relationship(
        back_populates="sourced_preferences"
    )
