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
from services.travel.plan_option_service import PlanOptionService


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
            title="鏉窞宸ヤ綔鍖?,
            status="active",
        )
        latest_assistant = SimpleNamespace(
            id=uuid.uuid4(),
            content="\n".join(
                [
                    "## 鏉窞涓ゆ棩鎱㈡父",
                    "鍏堥€涜タ婀栵紝鍐嶅幓娌冲潑琛椼€?,
                    "### 棰勭畻姹囨€?,
                    "- 浜哄潎绾?1200-1500 鍏?,
                    "### 娉ㄦ剰浜嬮」",
                    "- 瑗挎箹鐑棬鏃舵寤鸿鎻愬墠鍑哄彂",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 鏅偣涓茶仈璺嚎",
                            "- 鍩庡競锛氭澀宸?,
                            "- 鍑鸿鏂瑰紡锛氶┚杞?,
                            "- 鏅偣椤哄簭锛氳タ婀?-> 娌冲潑琛?,
                            "",
                            "### 鍒嗘鏄庣粏",
                            "| 娈佃惤 | 璧风偣 | 缁堢偣 | 璺濈 | 鑰楁椂 |",
                            "| --- | --- | --- | --- | --- |",
                            "| 1 | 瑗挎箹 | 娌冲潑琛?| 5.2 km | 18鍒嗛挓 |",
                            "",
                            "### 鎬讳綋浼扮畻",
                            "- 鎬昏窛绂伙細5.2 km",
                            "- 鎬昏€楁椂锛?8鍒嗛挓",
                            "- 璇存槑锛氳繖鏄垎娈甸€氬嫟鎬诲拰锛屾湭鍖呭惈鏅偣鍋滅暀鏃堕棿銆?,
                        ]
                    )
                ]
            },
        )

        get_latest_assistant_message.return_value = latest_assistant
        list_plan_options.return_value = []
        extract_candidate_plan_blocks.return_value = [
            {
                "title": "鏉窞涓ゆ棩鎱㈡父",
                "summary": "鍥寸粫瑗挎箹涓庢渤鍧婅灞曞紑鐨勪袱鏃ユ柟妗堛€?,
                "plan_markdown": "## 鏉窞涓ゆ棩鎱㈡父\n鍏堥€涜タ婀栵紝鍐嶅幓娌冲潑琛椼€?,
                "primary_destination": "鏉窞",
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
            ["瑗挎箹", "娌冲潑琛?],
            structured_context["amap"]["routes"][0]["spot_sequence"],
        )
        self.assertEqual(
            str(latest_assistant.id),
            structured_context["amap"]["source_message_id"],
        )


if __name__ == "__main__":
    unittest.main()
