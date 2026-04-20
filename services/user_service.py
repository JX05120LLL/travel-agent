"""User service."""

from __future__ import annotations

import os
import uuid

from sqlalchemy.orm import Session

from db.models import User
from db.repositories.user_repository import add_user, get_user_by_id, get_user_by_username

DEMO_USERNAME = os.getenv("DEMO_USERNAME", "demo_user")
DEMO_DISPLAY_NAME = os.getenv("DEMO_DISPLAY_NAME", "demo_user")
DEMO_EMAIL = os.getenv("DEMO_EMAIL")
DEMO_PASSWORD_HASH = os.getenv("DEMO_PASSWORD_HASH", "demo_not_for_login")


class UserService:
    """Application service for user lookup and demo-user fallback."""

    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(
        self,
        *,
        user_id: uuid.UUID,
    ) -> User | None:
        return get_user_by_id(self.db, user_id)

    def get_or_create_demo_user(self) -> User:
        user = get_user_by_username(self.db, DEMO_USERNAME)
        if user is not None:
            return user

        user = User(
            username=DEMO_USERNAME,
            email=DEMO_EMAIL,
            password_hash=DEMO_PASSWORD_HASH,
            display_name=DEMO_DISPLAY_NAME,
            status="active",
        )
        add_user(self.db, user)
        self.db.commit()
        self.db.refresh(user)
        return user
