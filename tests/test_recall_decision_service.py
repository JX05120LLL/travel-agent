import sys
import types
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    sys.modules["httpx"] = httpx_module

if "langchain_core.tools" not in sys.modules:
    langchain_core = sys.modules.get("langchain_core") or types.ModuleType("langchain_core")
    tools_module = types.ModuleType("langchain_core.tools")

    def tool(func=None, *args, **kwargs):
        if func is None:
            return lambda inner: inner
        return func

    tools_module.tool = tool
    langchain_core.tools = tools_module
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.tools"] = tools_module

from services.recall_service import RecallService


class RecallDecisionServiceTests(unittest.TestCase):
    @patch("services.recall_service.add_history_recall_log")
    @patch("services.recall_service.score_recall_candidate")
    @patch("services.recall_service.list_active_user_preferences")
    @patch("services.recall_service.list_user_sessions_for_recall")
    @patch("services.recall_service.list_user_plan_options_for_recall")
    @patch("services.recall_service.list_user_trips")
    def test_search_history_marks_blocked_matches_as_reference_only_for_runtime_governance(
        self,
        list_user_trips,
        list_plan_options,
        list_sessions,
        list_preferences,
        score_recall_candidate,
        add_history_recall_log,
    ):
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        trip = SimpleNamespace(
            id=uuid.uuid4(),
            title="国庆北京历史行程",
            primary_destination="北京",
            summary="国庆北京 4 天方案",
            plan_markdown="国庆北京 4 天方案",
            destinations=[SimpleNamespace(destination_name="北京")],
            preferences={},
            total_days=4,
            travel_start_date=None,
            travel_end_date=None,
        )
        list_user_trips.return_value = [trip]
        list_plan_options.return_value = []
        list_sessions.return_value = []
        list_preferences.return_value = []
        score_recall_candidate.return_value = (
            0.82,
            ["目的地匹配:北京", "偏好冲突:budget.level"],
        )
        add_history_recall_log.side_effect = lambda db, log: log

        service = RecallService(db=MagicMock())
        result = service.search_history(
            user_id=user_id,
            query_text="帮我找北京方案，但这次预算尽量省钱",
            session_id=session_id,
        )

        self.assertTrue(result["decision_groups"]["blocked"])
        blocked_item = result["decision_groups"]["blocked"][0]
        self.assertEqual("blocked", blocked_item["adoption_level"])
        self.assertTrue(blocked_item["blocking_reasons"])
        self.assertIn("暂不直接沿用", result["decision_summary"])


if __name__ == "__main__":
    unittest.main()
