"""方案比较项模型。"""

from __future__ import annotations

from db.models.common import (
    DateTime,
    Decimal,
    ForeignKey,
    Integer,
    JSONB,
    Mapped,
    Numeric,
    Text,
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


class PlanComparisonItem(Base):
    """方案比较中的单个候选项。"""

    __tablename__ = "plan_comparison_items"

    __table_args__ = (
        UniqueConstraint(
            "comparison_id",
            "plan_option_id",
            name="uq_plan_comparison_items_option",
        ),
        UniqueConstraint(
            "comparison_id",
            "sequence_no",
            name="uq_plan_comparison_items_sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_comparisons.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_options.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    pros: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    cons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    comparison: Mapped["PlanComparison"] = relationship(back_populates="items")
    plan_option: Mapped["PlanOption"] = relationship(back_populates="comparison_items")
