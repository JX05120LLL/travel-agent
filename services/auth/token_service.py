"""JWT 访问令牌服务。"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()


class TokenServiceConfigError(RuntimeError):
    """JWT 配置缺失时抛出。"""


class InvalidAccessTokenError(RuntimeError):
    """访问令牌无效或已过期。"""


def _read_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 1)


class TokenService:
    """负责签发和解析访问令牌。"""

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        algorithm: str | None = None,
        expire_minutes: int | None = None,
    ):
        resolved_secret = (secret_key or os.getenv("JWT_SECRET_KEY") or "").strip()
        if not resolved_secret:
            raise TokenServiceConfigError("未配置 JWT_SECRET_KEY，无法启动 Web 鉴权。")

        self.secret_key = resolved_secret
        self.algorithm = (algorithm or os.getenv("JWT_ALGORITHM") or "HS256").strip() or "HS256"
        self.expire_minutes = max(
            expire_minutes
            if expire_minutes is not None
            else _read_positive_int(os.getenv("JWT_EXPIRE_MINUTES"), 10080),
            1,
        )

    @property
    def expires_in_seconds(self) -> int:
        return self.expire_minutes * 60

    def create_access_token(self, *, user_id: uuid.UUID, username: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "username": username,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self.expire_minutes)).timestamp()),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_access_token(self, token: str) -> dict:
        normalized_token = (token or "").strip()
        if not normalized_token:
            raise InvalidAccessTokenError("访问令牌不能为空。")
        try:
            payload = jwt.decode(
                normalized_token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
        except JWTError as exc:
            raise InvalidAccessTokenError("访问令牌无效或已过期。") from exc

        if payload.get("type") != "access":
            raise InvalidAccessTokenError("访问令牌类型不正确。")
        if not payload.get("sub"):
            raise InvalidAccessTokenError("访问令牌缺少用户标识。")
        return payload
