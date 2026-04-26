import sys
import types
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    httpx_module.get = MagicMock()
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

if "langchain_core.messages" not in sys.modules:
    langchain_core = sys.modules.get("langchain_core") or types.ModuleType("langchain_core")
    messages_module = types.ModuleType("langchain_core.messages")

    class _Message:
        def __init__(self, content=None):
            self.content = content

    messages_module.AIMessage = _Message
    messages_module.HumanMessage = _Message
    messages_module.SystemMessage = _Message
    langchain_core.messages = messages_module
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.messages"] = messages_module

from db.models import ChatSession
from services.plan_option_service import PlanOptionService


class PlanOptionServiceTests(unittest.TestCase):
    @patch("services.plan_option_service.extract_candidate_plan_blocks_with_city_fallback")
    @patch("services.plan_option_service.get_latest_assistant_message")
    @patch("services.plan_option_service.list_plan_options")
    def test_create_options_from_latest_message_attaches_structured_amap_context(
        self,
        list_plan_options,
        get_latest_assistant_message,
        extract_candidate_plan_blocks,
    ):
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="杭州工作区",
            status="active",
        )
        latest_assistant = SimpleNamespace(
            id=uuid.uuid4(),
            content="\n".join(
                [
                    "## 杭州两日慢游",
                    "先逛西湖，再去河坊街。",
                    "### 预算汇总",
                    "- 人均约 1200-1500 元",
                    "### 注意事项",
                    "- 西湖热门时段建议提前出发",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 景点串联路线",
                            "- 城市：杭州",
                            "- 出行方式：驾车",
                            "- 景点顺序：西湖 -> 河坊街",
                            "",
                            "### 分段明细",
                            "| 段落 | 起点 | 终点 | 距离 | 耗时 |",
                            "| --- | --- | --- | --- | --- |",
                            "| 1 | 西湖 | 河坊街 | 5.2 km | 18分钟 |",
                            "",
                            "### 总体估算",
                            "- 总距离：5.2 km",
                            "- 总耗时：18分钟",
                            "- 说明：这是分段通勤总和，未包含景点停留时间。",
                        ]
                    )
                ]
            },
        )

        get_latest_assistant_message.return_value = latest_assistant
        list_plan_options.return_value = []
        extract_candidate_plan_blocks.return_value = [
            {
                "title": "杭州两日慢游",
                "summary": "围绕西湖与河坊街展开的两日方案。",
                "plan_markdown": "## 杭州两日慢游\n先逛西湖，再去河坊街。",
                "primary_destination": "杭州",
            }
        ]

        service = PlanOptionService(db=MagicMock())
        service.session_service = MagicMock()
        service.session_service.get_session_or_raise.return_value = session
        service.memory_service = MagicMock()
        service._create_plan_option = MagicMock(return_value=SimpleNamespace(id=uuid.uuid4()))
        service.build_branch_view = MagicMock(side_effect=lambda item: item)

        result = service.create_options_from_latest_message(
            session_id=session.id,
            user_id=session.user_id,
            commit=False,
        )

        self.assertEqual(1, len(result))
        _, kwargs = service._create_plan_option.call_args
        structured_context = kwargs["constraints"]["structured_context"]
        self.assertIn("amap", structured_context)
        self.assertIn("assistant_plan", structured_context)
        self.assertEqual("spot_route", structured_context["amap"]["cards"][0]["type"])
        self.assertEqual("budget_summary", structured_context["assistant_plan"]["cards"][0]["type"])
        self.assertEqual(
            ["西湖", "河坊街"],
            structured_context["amap"]["routes"][0]["spot_sequence"],
        )
        self.assertEqual(
            str(latest_assistant.id),
            structured_context["amap"]["source_message_id"],
        )


if __name__ == "__main__":
    unittest.main()
