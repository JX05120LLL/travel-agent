"""Database engine and session factory."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()


def get_database_url() -> str:
    """Read DATABASE_URL from env and fail fast if it is missing."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "未找到 DATABASE_URL，请先在 .env 中配置 PostgreSQL 连接串。"
        )
    return database_url


DATABASE_URL = get_database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

