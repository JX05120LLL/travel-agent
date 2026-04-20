"""用户模型。"""

from __future__ import annotations

from db.models.common import (
    CheckConstraint,
    DateTime,
    Mapped,
    String,
    UUID,
    datetime,
    func,
    mapped_column,
    relationship,
    uuid,
)
from db.base import Base


class User(Base):
    """系统用户。"""

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="chk_users_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="user")
    plan_options: Mapped[list["PlanOption"]] = relationship(back_populates="user")
    plan_comparisons: Mapped[list["PlanComparison"]] = relationship(
        back_populates="user"
    )
    trips: Mapped[list["Trip"]] = relationship(back_populates="user")
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user")
    history_recall_logs: Mapped[list["HistoryRecallLog"]] = relationship(
        back_populates="user"
    )
    session_events: Mapped[list["SessionEvent"]] = relationship(back_populates="user")
