import importlib.util
import unittest

STARLETTE_AVAILABLE = importlib.util.find_spec("starlette") is not None

if STARLETTE_AVAILABLE:
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from mcp_wrapper.auth import BearerTokenAuthMiddleware


@unittest.skipUnless(STARLETTE_AVAILABLE, "starlette 未安装，跳过 MCP auth 测试")
class BearerTokenAuthMiddlewareTests(unittest.TestCase):
    def test_invalid_bearer_token_is_rejected(self):
        async def ok(_request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/mcp", ok)])
        app.add_middleware(
            BearerTokenAuthMiddleware,
            expected_token="secret-token",
            protected_path="/mcp",
        )
        client = TestClient(app)

        response = client.get("/mcp", headers={"Authorization": "Bearer wrong-token"})

        self.assertEqual(401, response.status_code)
        self.assertEqual("unauthorized", response.json()["error"])

    def test_valid_bearer_token_is_allowed(self):
        async def ok(_request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/mcp", ok)])
        app.add_middleware(
            BearerTokenAuthMiddleware,
            expected_token="secret-token",
            protected_path="/mcp",
        )
        client = TestClient(app)

        response = client.get("/mcp", headers={"Authorization": "Bearer secret-token"})

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["ok"])
