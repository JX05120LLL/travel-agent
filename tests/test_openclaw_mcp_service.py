import sys
import types
import unittest
import uuid
from types import SimpleNamespace

langchain_core = sys.modules.get("langchain_core")
if langchain_core is None:
    langchain_core = types.ModuleType("langchain_core")
    sys.modules["langchain_core"] = langchain_core

if "langchain_core.messages" not in sys.modules:
    messages_module = types.ModuleType("langchain_core.messages")

    class _Message:
        def __init__(self, content=None):
            self.content = content

    messages_module.AIMessage = _Message
    messages_module.HumanMessage = _Message
    messages_module.SystemMessage = _Message
    sys.modules["langchain_core.messages"] = messages_module
    langchain_core.messages = messages_module

if "langchain_core.tools" not in sys.modules:
    tools_module = types.ModuleType("langchain_core.tools")

    def tool(func=None, *args, **kwargs):
        if func is None:
            return lambda inner: inner
        return func

    tools_module.tool = tool
    sys.modules["langchain_core.tools"] = tools_module
    langchain_core.tools = tools_module

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

from services.channels.openclaw_mcp_service import OpenClawMcpService


class OpenClawMcpServiceTests(unittest.TestCase):
    def test_travel_chat_returns_runner_result_shape(self):
        service = OpenClawMcpService(db=object())
        binding = SimpleNamespace(
            user=SimpleNamespace(id=uuid.uuid4()),
            session=SimpleNamespace(id=uuid.uuid4()),
            is_new_session=True,
        )
        service.mapping_service = SimpleNamespace(
            resolve_or_create_binding=lambda **_: binding
        )
        service.chat_turn_runner = SimpleNamespace(
            run_turn=lambda **_: SimpleNamespace(
                status="ok",
                degraded_reason=None,
                session_id=str(binding.session.id),
                reply="杭州三天轻松游先给你一版",
                workspace_payload={
                    "active_trip_id": str(uuid.uuid4()),
                    "active_trip_title": "杭州三天轻松游",
                },
            )
        )

        payload = service.travel_chat(
            external_user_id="wx_u_1",
            conversation_id="conv_1",
            message="帮我规划杭州三天",
        )

        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["is_new_session"])
        self.assertTrue(payload["trip_ready"])
        self.assertEqual("杭州三天轻松游", payload["active_trip_title"])

    def test_travel_get_active_trip_returns_found_false_when_trip_missing(self):
        service = OpenClawMcpService(db=object())
        binding = SimpleNamespace(
            user=SimpleNamespace(id=uuid.uuid4()),
            session=SimpleNamespace(id=uuid.uuid4()),
        )
        service.mapping_service = SimpleNamespace(
            get_binding_or_none=lambda **_: binding
        )
        service.trip_service = SimpleNamespace(get_active_trip=lambda **_: None)

        payload = service.travel_get_active_trip(
            external_user_id="wx_u_1",
            conversation_id="conv_1",
        )

        self.assertFalse(payload["found"])
        self.assertFalse(payload["trip_ready"])

    def test_travel_export_markdown_defaults_to_active_trip(self):
        service = OpenClawMcpService(db=object())
        trip = SimpleNamespace(id=uuid.uuid4(), title="杭州三天轻松游")
        binding = SimpleNamespace(
            user=SimpleNamespace(id=uuid.uuid4()),
            session=SimpleNamespace(id=uuid.uuid4()),
        )
        service.mapping_service = SimpleNamespace(
            get_binding_or_none=lambda **_: binding
        )
        service.trip_service = SimpleNamespace(
            get_active_trip=lambda **_: trip,
            get_trip_or_raise=lambda **_: trip,
        )
        service.trip_export_service = SimpleNamespace(
            ensure_document_markdown=lambda _: "# 杭州三天轻松游",
            build_markdown_filename=lambda _: "hangzhou-3d.md",
        )

        payload = service.travel_export_markdown(
            external_user_id="wx_u_1",
            conversation_id="conv_1",
            trip_id=None,
        )

        self.assertTrue(payload["found"])
        self.assertEqual("hangzhou-3d.md", payload["filename"])
        self.assertIn("杭州三天轻松游", payload["markdown"])
