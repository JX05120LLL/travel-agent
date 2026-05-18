"""OpenClaw MCP wrapper 的鉴权辅助逻辑。"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    """用静态 Bearer Token 保护 MCP 路径。"""

    def __init__(self, app, *, expected_token: str, protected_path: str):
        super().__init__(app)
        self.expected_token = (expected_token or "").strip()
        normalized_path = (protected_path or "/mcp").strip() or "/mcp"
        self.protected_path = (
            normalized_path if normalized_path.startswith("/") else f"/{normalized_path}"
        )

    async def dispatch(self, request: Request, call_next):
        """拦截 MCP 请求并校验 Bearer Token。"""
        if request.url.path.startswith(self.protected_path):
            if not self.expected_token:
                return JSONResponse(
                    {"error": "mcp_wrapper_auth_token_missing"},
                    status_code=500,
                )
            auth_header = request.headers.get("Authorization", "")
            expected_header = f"Bearer {self.expected_token}"
            if auth_header != expected_header:
                return JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)
