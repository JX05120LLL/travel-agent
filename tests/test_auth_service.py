import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from db.models import User
from services.auth.auth_service import (
    AuthDisabledUserError,
    AuthInvalidCredentialsError,
    AuthService,
    DuplicateUsernameError,
)
from services.auth.password_service import PasswordService
from services.auth.token_service import InvalidAccessTokenError, TokenService


def build_user(*, username: str, password: str, status: str = "active") -> User:
    password_service = PasswordService()
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=None,
        password_hash=password_service.hash_password(password),
        display_name=username,
        status=status,
    )
    user.created_at = datetime.now(timezone.utc)
    user.last_login_at = None
    return user


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.token_service = TokenService(
            secret_key="test-secret",
            algorithm="HS256",
            expire_minutes=30,
        )

    @patch("services.auth.auth_service.add_user")
    @patch("services.auth.auth_service.get_user_by_username")
    def test_register_user_hashes_password_and_commits(self, get_user_by_username, add_user):
        get_user_by_username.return_value = None

        def fake_add_user(_db, user):
            user.created_at = datetime.now(timezone.utc)
            user.last_login_at = None
            return user

        add_user.side_effect = fake_add_user
        service = AuthService(self.db, token_service=self.token_service)

        user = service.register_user(username="alice_01", password="secret123")

        self.assertEqual("alice_01", user.username)
        self.assertNotEqual("secret123", user.password_hash)
        self.assertTrue(PasswordService().verify_password("secret123", user.password_hash))
        self.db.commit.assert_called_once()
        self.db.refresh.assert_called_once_with(user)

    @patch("services.auth.auth_service.get_user_by_username")
    def test_register_user_rejects_duplicate_username(self, get_user_by_username):
        get_user_by_username.return_value = build_user(username="alice_01", password="secret123")
        service = AuthService(self.db, token_service=self.token_service)

        with self.assertRaises(DuplicateUsernameError):
            service.register_user(username="alice_01", password="secret123")

    @patch("services.auth.auth_service.get_user_by_username")
    def test_login_user_returns_token_and_updates_last_login(self, get_user_by_username):
        user = build_user(username="alice_01", password="secret123")
        get_user_by_username.return_value = user
        service = AuthService(self.db, token_service=self.token_service)

        result = service.login_user(username="alice_01", password="secret123")

        self.assertEqual(user, result.user)
        self.assertEqual("bearer", result.token_type)
        self.assertTrue(result.access_token)
        self.assertEqual(self.token_service.expires_in_seconds, result.expires_in)
        self.assertIsNotNone(user.last_login_at)
        payload = self.token_service.decode_access_token(result.access_token)
        self.assertEqual(str(user.id), payload["sub"])
        self.db.commit.assert_called_once()
        self.db.refresh.assert_called_once_with(user)

    @patch("services.auth.auth_service.get_user_by_username")
    def test_login_user_rejects_wrong_password(self, get_user_by_username):
        get_user_by_username.return_value = build_user(
            username="alice_01",
            password="secret123",
        )
        service = AuthService(self.db, token_service=self.token_service)

        with self.assertRaises(AuthInvalidCredentialsError):
            service.login_user(username="alice_01", password="wrong-pass")

    @patch("services.auth.auth_service.get_user_by_username")
    def test_login_user_rejects_disabled_account(self, get_user_by_username):
        get_user_by_username.return_value = build_user(
            username="alice_01",
            password="secret123",
            status="disabled",
        )
        service = AuthService(self.db, token_service=self.token_service)

        with self.assertRaises(AuthDisabledUserError):
            service.login_user(username="alice_01", password="secret123")

    @patch("services.auth.auth_service.get_user_by_id")
    def test_authenticate_access_token_returns_user(self, get_user_by_id):
        user = build_user(username="alice_01", password="secret123")
        get_user_by_id.return_value = user
        service = AuthService(self.db, token_service=self.token_service)
        token = self.token_service.create_access_token(
            user_id=user.id,
            username=user.username,
        )

        result = service.authenticate_access_token(token)

        self.assertEqual(user, result)

    @patch("services.auth.auth_service.get_user_by_id")
    def test_authenticate_access_token_rejects_missing_user(self, get_user_by_id):
        get_user_by_id.return_value = None
        service = AuthService(self.db, token_service=self.token_service)
        token = self.token_service.create_access_token(
            user_id=uuid.uuid4(),
            username="alice_01",
        )

        with self.assertRaises(InvalidAccessTokenError):
            service.authenticate_access_token(token)


if __name__ == "__main__":
    unittest.main()
