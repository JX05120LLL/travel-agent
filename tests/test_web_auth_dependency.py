import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

import web.auth as web_auth
from db.models import User


def build_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/sessions",
            "headers": [],
        }
    )


def build_user() -> User:
    user = User(
        id=uuid.uuid4(),
        username="alice_01",
        email=None,
        password_hash="hashed",
        display_name="alice_01",
        status="active",
    )
    user.created_at = datetime.now(timezone.utc)
    return user


class WebAuthDependencyTests(unittest.TestCase):
    @patch("web.auth.AuthService")
    def test_get_current_user_accepts_valid_bearer_token(self, auth_service_cls):
        user = build_user()
        auth_service_cls.return_value.authenticate_access_token.return_value = user
        request = build_request()

        result = web_auth.get_current_user(
            request=request,
            db=object(),
            authorization="Bearer valid-token",
            x_user_id=None,
            x_demo_user=None,
        )

        self.assertEqual(user, result)
        self.assertEqual("bearer", request.state.auth_mode)

    @patch("web.auth.AuthService")
    def test_get_current_user_rejects_invalid_bearer_token(self, auth_service_cls):
        auth_service_cls.return_value.authenticate_access_token.side_effect = (
            web_auth.InvalidAccessTokenError("访问令牌无效或已过期。")
        )

        with self.assertRaises(HTTPException) as context:
            web_auth.get_current_user(
                request=build_request(),
                db=object(),
                authorization="Bearer invalid-token",
                x_user_id=None,
                x_demo_user=None,
            )

        self.assertEqual(401, context.exception.status_code)

    @patch("web.auth.AuthService")
    def test_get_current_user_rejects_when_no_credentials(self, auth_service_cls):
        with patch.object(web_auth, "AUTH_DEV_FALLBACK_ENABLED", False):
            with self.assertRaises(HTTPException) as context:
                web_auth.get_current_user(
                    request=build_request(),
                    db=object(),
                    authorization=None,
                    x_user_id=None,
                    x_demo_user=None,
                )

        self.assertEqual(401, context.exception.status_code)
        auth_service_cls.assert_called_once()

    @patch("web.auth.UserService")
    @patch("web.auth.AuthService")
    def test_get_current_user_allows_explicit_demo_header_in_dev(
        self,
        auth_service_cls,
        user_service_cls,
    ):
        demo_user = build_user()
        user_service_cls.return_value.get_or_create_demo_user.return_value = demo_user
        request = build_request()

        with patch.object(web_auth, "AUTH_DEV_FALLBACK_ENABLED", True):
            result = web_auth.get_current_user(
                request=request,
                db=object(),
                authorization=None,
                x_user_id=None,
                x_demo_user="true",
            )

        self.assertEqual(demo_user, result)
        self.assertEqual("demo", request.state.auth_mode)
        auth_service_cls.assert_called_once()


if __name__ == "__main__":
    unittest.main()
