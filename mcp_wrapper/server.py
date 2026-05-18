"""独立的 HTTP MCP wrapper，供 OpenClaw 调用。"""

from __future__ import annotations

import contextlib
import os

import uvicorn
from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from db.session import SessionLocal
from mcp_wrapper.auth import BearerTokenAuthMiddleware
from services.channels.openclaw_mcp_service import OpenClawMcpService

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except Exception:  # pragma: no cover - 某些本地测试环境可能没有安装 mcp
    FastMCP = None  # type: ignore[assignment]
    MCP_AVAILABLE = False


def _normalize_path(value: str, default: str) -> str:
    """确保路径以 `/` 开头。"""
    raw = (value or default).strip() or default
    return raw if raw.startswith("/") else f"/{raw}"


MCP_WRAPPER_HOST = os.getenv("MCP_WRAPPER_HOST", "0.0.0.0")
MCP_WRAPPER_PORT = int(os.getenv("MCP_WRAPPER_PORT", "7861"))
MCP_WRAPPER_PATH = _normalize_path(os.getenv("MCP_WRAPPER_PATH", "/mcp"), "/mcp")
MCP_WRAPPER_AUTH_TOKEN = os.getenv("MCP_WRAPPER_AUTH_TOKEN", "")


def _build_service() -> OpenClawMcpService:
    """为一次请求创建业务 service。"""
    db = SessionLocal()
    try:
        return OpenClawMcpService(db)
    except Exception:
        db.close()
        raise


def _call_service(method_name: str, **kwargs):
    """调用业务 service，并在结束后关闭数据库连接。"""
    service = _build_service()
    try:
        return getattr(service, method_name)(**kwargs)
    finally:
        service.db.close()


def build_mcp_server():
    """构建 FastMCP 服务对象。"""
    if not MCP_AVAILABLE:
        return None

    mcp = FastMCP(
        "travel-agent",
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
    )

    @mcp.tool
    def travel_chat(
        external_user_id: str,
        conversation_id: str,
        message: str,
    ) -> dict:
        """聊天入口：让 OpenClaw 驱动 travel-agent 完成一轮规划。"""
        try:
            return _call_service(
                "travel_chat",
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                message=message,
            )
        except Exception as exc:
            return {
                "status": "error",
                "degraded_reason": "unexpected_error",
                "reply": str(exc),
                "session_id": None,
                "is_new_session": False,
                "active_trip_id": None,
                "active_trip_title": None,
                "trip_ready": False,
            }

    @mcp.tool
    def travel_get_active_trip(
        external_user_id: str,
        conversation_id: str,
    ) -> dict:
        """查询当前外部会话绑定的正式行程。"""
        return _call_service(
            "travel_get_active_trip",
            external_user_id=external_user_id,
            conversation_id=conversation_id,
        )

    @mcp.tool
    def travel_export_markdown(
        external_user_id: str,
        conversation_id: str,
        trip_id: str | None = None,
    ) -> dict:
        """导出当前会话或指定 trip 的 Markdown。"""
        try:
            return _call_service(
                "travel_export_markdown",
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                trip_id=trip_id,
            )
        except ValueError as exc:
            return {
                "found": False,
                "message": str(exc),
            }

    return mcp


async def health(_request):
    """健康检查接口。"""
    return JSONResponse(
        {
            "ok": True,
            "mcp_available": MCP_AVAILABLE,
            "path": MCP_WRAPPER_PATH,
        }
    )


def create_app():
    """创建 Starlette 应用。"""
    middleware = [
        Middleware(
            BearerTokenAuthMiddleware,
            expected_token=MCP_WRAPPER_AUTH_TOKEN,
            protected_path=MCP_WRAPPER_PATH,
        )
    ]

    if not MCP_AVAILABLE:

        async def missing_mcp(_request):
            raise HTTPException(
                status_code=500,
                detail="当前环境未安装 Python MCP SDK，请先执行 pip install -r requirements.txt",
            )

        return Starlette(
            routes=[
                Route("/health", health),
                Route(MCP_WRAPPER_PATH, missing_mcp, methods=["GET", "POST", "DELETE"]),
            ],
            middleware=middleware,
        )

    mcp = build_mcp_server()

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/health", health),
            Mount(MCP_WRAPPER_PATH, app=mcp.streamable_http_app()),
        ],
        middleware=middleware,
        lifespan=lifespan,
    )


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "mcp_wrapper.server:app",
        host=MCP_WRAPPER_HOST,
        port=MCP_WRAPPER_PORT,
        reload=False,
    )
