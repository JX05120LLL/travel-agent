import importlib.util
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None

if FASTAPI_AVAILABLE:
    from fastapi.testclient import TestClient

    import web.app as web_app
    from db.models import User
    from services.auth.auth_service import AuthLoginResult
    from services.core.errors import ServiceNotFoundError
else:  # pragma: no cover
    web_app = None
    User = object
    AuthLoginResult = object
    ServiceNotFoundError = Exception


def build_user(username: str = "alice_01") -> User:
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=None,
        password_hash="hashed",
        display_name=username,
        status="active",
    )
    user.created_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    return user


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi 未安装，跳过 Web 认证接口测试")
class WebAuthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(web_app.app)

    def tearDown(self):
        web_app.app.dependency_overrides.clear()

    @patch("web.app.AuthService")
    def test_register_endpoint_returns_created_user(self, auth_service_cls):
        user = build_user("new_user")
        auth_service_cls.return_value.register_user.return_value = user

        response = self.client.post(
            "/auth/register",
            json={"username": "new_user", "password": "secret123"},
        )

        self.assertEqual(201, response.status_code)
        payload = response.json()
        self.assertEqual("new_user", payload["username"])
        self.assertEqual(str(user.id), payload["id"])

    @patch("web.app.AuthService")
    def test_register_endpoint_maps_duplicate_username_to_409(self, auth_service_cls):
        auth_service_cls.return_value.register_user.side_effect = web_app.DuplicateUsernameError(
            "用户名已存在，请更换一个用户名。"
        )

        response = self.client.post(
            "/auth/register",
            json={"username": "new_user", "password": "secret123"},
        )

        self.assertEqual(409, response.status_code)

    @patch("web.app.AuthService")
    def test_login_endpoint_returns_token_payload(self, auth_service_cls):
        user = build_user("alice_01")
        auth_service_cls.return_value.login_user.return_value = AuthLoginResult(
            user=user,
            access_token="token-123",
            token_type="bearer",
            expires_in=604800,
        )

        response = self.client.post(
            "/auth/login",
            json={"username": "alice_01", "password": "secret123"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("token-123", payload["access_token"])
        self.assertEqual("bearer", payload["token_type"])
        self.assertEqual("alice_01", payload["user"]["username"])

    def test_protected_route_requires_token(self):
        response = self.client.get("/sessions")
        self.assertEqual(401, response.status_code)

    def test_auth_me_returns_current_user(self):
        user = build_user("alice_01")
        web_app.app.dependency_overrides[web_app.get_current_user] = lambda: user

        response = self.client.get("/auth/me")

        self.assertEqual(200, response.status_code)
        self.assertEqual("alice_01", response.json()["username"])

    @patch("web.app.SessionManagementService")
    def test_cross_user_session_access_returns_404(self, session_service_cls):
        user = build_user("user_b")
        session_id = uuid.uuid4()
        web_app.app.dependency_overrides[web_app.get_current_user] = lambda: user
        web_app.app.dependency_overrides[web_app.get_db] = lambda: object()
        session_service_cls.return_value.get_session_or_raise.side_effect = ServiceNotFoundError(
            "会话不存在或不属于当前用户"
        )

        response = self.client.get(f"/sessions/{session_id}/messages")

        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
