"""密码哈希服务。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PBKDF2_SCHEME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390000
SALT_BYTES = 16


class PasswordService:
    """统一处理密码哈希和校验。"""

    def hash_password(self, plain_password: str) -> str:
        salt = secrets.token_bytes(SALT_BYTES)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        if not plain_password or not password_hash:
            return False

        parts = password_hash.split("$")
        if len(parts) != 4:
            return False

        scheme, iterations_raw, salt_b64, digest_b64 = parts
        if scheme != PBKDF2_SCHEME:
            return False

        try:
            iterations = int(iterations_raw)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected_digest = base64.b64decode(digest_b64.encode("ascii"))
        except (TypeError, ValueError):
            return False

        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual_digest, expected_digest)
