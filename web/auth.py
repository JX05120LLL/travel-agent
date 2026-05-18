"""Web 层身份依赖。"""

from __future__ import annotations

import os
import uuid

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from db.models import User
from db.session import get_db
from services.auth import AuthDisabledUserError, AuthService, InvalidAccessTokenError
from services.session.user_service import UserService

AUTH_DEV_FALLBACK_ENABLED = os.getenv(
    "AUTH_DEV_FALLBACK_ENABLED",
    "true",
).lower() in {"1", "true", "yes", "on"}
ALLOW_HEADER_USER_ID = os.getenv("ALLOW_HEADER_USER_ID", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _is_truthy(value: str | None) -> bool:
    """统一处理布尔风格请求头。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_demo_user: str | None = Header(default=None, alias="X-Demo-User"),
) -> User:
    """解析当前请求对应的用户。"""
    user_service = UserService(db)
    auth_service = AuthService(db)

    normalized_authorization = (authorization or "").strip()
    if normalized_authorization:
        if not normalized_authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization 头格式不正确。")

        token = normalized_authorization[7:].strip()
        try:
            user = auth_service.authenticate_access_token(token)
        except InvalidAccessTokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except AuthDisabledUserError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        request.state.current_user = user
        request.state.auth_mode = "bearer"
        return user

    if AUTH_DEV_FALLBACK_ENABLED and ALLOW_HEADER_USER_ID and x_user_id:
        try:
            user_id = uuid.UUID(x_user_id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="X-User-Id 格式不正确。") from exc

        user = user_service.get_user_by_id(user_id=user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="当前请求用户不存在或不可用。")

        request.state.current_user = user
        request.state.auth_mode = "header_user_id"
        return user

    if AUTH_DEV_FALLBACK_ENABLED and _is_truthy(x_demo_user):
        user = user_service.get_or_create_demo_user()
        request.state.current_user = user
        request.state.auth_mode = "demo"
        return user

    raise HTTPException(status_code=401, detail="当前请求未通过身份校验。")
