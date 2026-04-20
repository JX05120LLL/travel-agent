"""模型层公共依赖。

把 ORM 模型里反复会用到的类型、函数、基础导入集中在这里，
这样每个实体文件就能更专注在自己的字段和关系定义上。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

__all__ = [
    "Any",
    "Base",
    "Boolean",
    "CheckConstraint",
    "Date",
    "DateTime",
    "Decimal",
    "ForeignKey",
    "Integer",
    "JSONB",
    "Mapped",
    "Numeric",
    "String",
    "Text",
    "UUID",
    "UniqueConstraint",
    "date",
    "datetime",
    "func",
    "mapped_column",
    "relationship",
    "text",
    "uuid",
]
