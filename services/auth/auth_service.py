"""注册、登录和访问令牌鉴权服务。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from db.models import User
from db.repositories.user_repository import add_user, get_user_by_id, get_user_by_username
from services.auth.password_service import PasswordService
from services.auth.token_service import InvalidAccessTokenError, TokenService

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128


class AuthValidationError(ValueError):
    """注册或登录参数不合法。"""


class DuplicateUsernameError(ValueError):
    """用户名已存在。"""


class AuthInvalidCredentialsError(ValueError):
    """用户名或密码错误。"""


class AuthDisabledUserError(ValueError):
    """账号被禁用。"""


@dataclass(slots=True)
class AuthLoginResult:
    """登录成功后的统一结果。"""

    user: User
    access_token: str
    token_type: str
    expires_in: int


class AuthService:
    """统一处理用户注册、登录和 token 鉴权。"""

    def __init__(
        self,
        db,
        *,
        password_service: PasswordService | None = None,
        token_service: TokenService | None = None,
    ):
        self.db = db
        self.password_service = password_service or PasswordService()
        self.token_service = token_service or TokenService()

    def register_user(self, *, username: str, password: str) -> User:
        normalized_username = self._normalize_username(username)
        normalized_password = self._normalize_password(password)

        existing_user = get_user_by_username(self.db, normalized_username)
        if existing_user is not None:
            raise DuplicateUsernameError("用户名已存在，请更换一个用户名。")

        user = User(
            username=normalized_username,
            email=None,
            password_hash=self.password_service.hash_password(normalized_password),
            display_name=normalized_username,
            status="active",
        )
        add_user(self.db, user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def login_user(self, *, username: str, password: str) -> AuthLoginResult:
        normalized_username = self._normalize_username(username)
        normalized_password = self._normalize_login_password(password)

        user = get_user_by_username(self.db, normalized_username)
        if user is None or not self.password_service.verify_password(
            normalized_password,
            user.password_hash,
        ):
            raise AuthInvalidCredentialsError("用户名或密码错误。")

        if user.status != "active":
            raise AuthDisabledUserError("当前账号已被禁用，暂时无法登录。")

        user.last_login_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(user)

        return AuthLoginResult(
            user=user,
            access_token=self.token_service.create_access_token(
                user_id=user.id,
                username=user.username,
            ),
            token_type="bearer",
            expires_in=self.token_service.expires_in_seconds,
        )

    def authenticate_access_token(self, token: str) -> User:
        payload = self.token_service.decode_access_token(token)
        try:
            user_id = uuid.UUID(str(payload["sub"]))
        except (TypeError, ValueError) as exc:
            raise InvalidAccessTokenError("访问令牌中的用户标识无效。") from exc

        user = get_user_by_id(self.db, user_id=user_id)
        if user is None:
            raise InvalidAccessTokenError("访问令牌对应的用户不存在。")
        if user.status != "active":
            raise AuthDisabledUserError("当前账号已被禁用，暂时无法访问。")
        return user

    def get_user_by_id(self, *, user_id: uuid.UUID) -> User | None:
        return get_user_by_id(self.db, user_id=user_id)

    def _normalize_username(self, username: str) -> str:
        normalized_username = (username or "").strip()
        if not USERNAME_PATTERN.fullmatch(normalized_username):
            raise AuthValidationError(
                "用户名需为 3-50 位，只能包含字母、数字、下划线、点和短横线。"
            )
        return normalized_username

    def _normalize_password(self, password: str) -> str:
        normalized_password = password or ""
        if len(normalized_password) < MIN_PASSWORD_LENGTH:
            raise AuthValidationError(f"密码至少需要 {MIN_PASSWORD_LENGTH} 位。")
        if len(normalized_password) > MAX_PASSWORD_LENGTH:
            raise AuthValidationError(f"密码长度不能超过 {MAX_PASSWORD_LENGTH} 位。")
        return normalized_password

    def _normalize_login_password(self, password: str) -> str:
        normalized_password = password or ""
        if not normalized_password:
            raise AuthValidationError("密码不能为空。")
        if len(normalized_password) > MAX_PASSWORD_LENGTH:
            raise AuthValidationError(f"密码长度不能超过 {MAX_PASSWORD_LENGTH} 位。")
        return normalized_password
