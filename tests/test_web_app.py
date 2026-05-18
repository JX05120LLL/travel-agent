import importlib.util
import unittest
from unittest.mock import patch


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None

if FASTAPI_AVAILABLE:
    from fastapi.testclient import TestClient


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi 未安装，跳过 web.app 相关测试")
class WebAppSmokeTests(unittest.TestCase):
    def test_web_app_can_be_imported(self):
        import web.app as web_app

        self.assertIsNotNone(web_app.app)

    def test_guardrail_message_keeps_partial_answer_and_reason(self):
        import web.app as web_app

        message = web_app._build_agent_guardrail_message(
            reason="工具调用已达到上限 16 次。",
            partial_answer="这是阶段性结果",
        )

        self.assertIn("这是阶段性结果", message)
        self.assertIn("工具调用已达到上限 16 次", message)
        self.assertIn("系统兜底说明", message)

    @patch("web.app.ChatTurnRunner")
    def test_chat_endpoint_streams_runner_events(self, runner_cls):
        import web.app as web_app
        from services.chat.chat_turn_runner import ChatTurnEvent

        user = web_app.User(
            id=__import__("uuid").uuid4(),
            username="demo_user",
            email=None,
            password_hash="x",
            display_name="demo",
            status="active",
        )
        web_app.app.dependency_overrides[web_app.get_current_user] = lambda: user
        web_app.app.dependency_overrides[web_app.get_db] = lambda: object()

        try:
            runner = runner_cls.return_value
            runner.stream_turn.return_value = iter(
                [
                    ChatTurnEvent(
                        "session",
                        {"session_id": "s1", "is_new": True, "title": "杭州"},
                    ),
                    ChatTurnEvent(
                        "token",
                        {"content": "杭州三天轻松游"},
                    ),
                    ChatTurnEvent(
                        "done",
                        {"status": "ok"},
                    ),
                ]
            )
            client = TestClient(web_app.app)

            response = client.post(
                "/chat",
                data={"message": "帮我规划杭州三天", "history": "[]", "session_id": ""},
            )

            self.assertEqual(200, response.status_code)
            self.assertIn("event: session", response.text)
            self.assertIn("event: token", response.text)
            self.assertIn("杭州三天轻松游", response.text)
        finally:
            web_app.app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
