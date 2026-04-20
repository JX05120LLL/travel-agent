"""历史召回日志模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
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
    datetime,
    func,
    mapped_column,
    relationship,
    text,
    uuid,
)
from db.base import Base


class HistoryRecallLog(Base):
    """跨会话召回的审计日志。"""

    __tablename__ = "history_recall_logs"

    __table_args__ = (
        CheckConstraint(
            "recall_type IN ('trip', 'plan_option', 'session', 'preference', 'none')",
            name="chk_history_recall_logs_type",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="chk_history_recall_logs_confidence",
        ),
        CheckConstraint(
            "matched_count >= 0",
            name="chk_history_recall_logs_matched_count",
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
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    recall_type: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    matched_record_type: Mapped[str | None] = mapped_column(String(30))
    matched_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    matched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    recall_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="history_recall_logs")
    session: Mapped["ChatSession | None"] = relationship(
        back_populates="history_recall_logs"
    )
