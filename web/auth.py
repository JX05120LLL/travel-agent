"""Web 层用户身份依赖。

当前阶段先兼容 demo user，但把“当前用户是谁”的判定集中到这里，
后续接 JWT / Session / OAuth 时，只需要替换这一层。
"""

from __future__ import annotations

import os
import uuid

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from db.models import User
from db.session import get_db
from services.user_service import UserService

ALLOW_HEADER_USER_ID = os.getenv("ALLOW_HEADER_USER_ID", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _is_truthy(value: str | None) -> bool:
    """统一处理布尔风格请求头，减少后续切换认证方案时的分支噪音。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_demo_user: str | None = Header(default=None, alias="X-Demo-User"),
) -> User:
    """解析当前请求对应的用户。

    设计思路：
    1. 未来优先接真实认证，这里会变成“验 token -> 查用户”。
    2. 当前为了兼容现有 demo 流程，默认仍回退到 demo user。
    3. 额外保留 `X-User-Id` 入口，方便在不改业务代码的前提下做灰度联调。
    """
    user_service = UserService(db)

    if ALLOW_HEADER_USER_ID and x_user_id:
        try:
            user_id = uuid.UUID(x_user_id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="X-User-Id 格式不正确") from exc

        user = user_service.get_user_by_id(user_id=user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="当前请求用户不存在或不可用")

        request.state.current_user = user
        request.state.auth_mode = "header_user_id"
        return user

    if _is_truthy(x_demo_user) or not x_user_id:
        user = user_service.get_or_create_demo_user()
        request.state.current_user = user
        request.state.auth_mode = "demo"
        return user

    raise HTTPException(status_code=401, detail="当前请求未通过身份校验")
