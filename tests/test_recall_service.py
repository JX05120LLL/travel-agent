import unittest
import uuid
import sys
import types
from datetime import datetime
from decimal import Decimal
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

from db.models import UserPreference
from services.recall_service import RecallService


def build_preference() -> UserPreference:
    preference = UserPreference(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        preference_category="budget",
        preference_key="level",
        preference_value={"value": "economy", "label": "预算偏经济", "evidence": "预算有限"},
        source="user_explicit",
        confidence=Decimal("0.92"),
        is_active=True,
    )
    preference.updated_at = datetime(2026, 4, 20, 12, 0, 0)
    return preference


class RecallServiceTests(unittest.TestCase):
    @patch("services.recall_service.build_query_profile")
    @patch("services.recall_service.resolve_holiday_window")
    @patch("services.recall_service.contains_holiday_keyword")
    @patch("services.recall_service.add_history_recall_log")
    @patch("services.recall_service.list_active_user_preferences")
    @patch("services.recall_service.list_user_sessions_for_recall")
    @patch("services.recall_service.list_user_plan_options_for_recall")
    @patch("services.recall_service.list_user_trips")
    def test_search_history_passes_resolved_holiday_window_into_profile(
        self,
        list_user_trips,
        list_plan_options,
        list_sessions,
        list_preferences,
        add_history_recall_log,
        contains_holiday_keyword,
        resolve_holiday_window,
        build_query_profile,
    ):
        contains_holiday_keyword.return_value = True
        resolve_holiday_window.return_value = {
            "holiday_name": "国庆节",
            "start_date": "2026-10-01",
            "end_date": "2026-10-07",
            "off_day_ranges": [("2026-10-01", "2026-10-07")],
        }
        build_query_profile.return_value = SimpleNamespace(
            cleaned_query="国庆北京",
            query_tokens={"国庆", "北京"},
            destinations=["北京"],
            preference_identities=set(),
            preference_fact_map={},
            day_count=None,
            specific_dates=set(),
            holiday_window_dates={(10, 1), (10, 2)},
            travel_months={10},
            weekend_trip=None,
            holiday_labels={"national_day"},
            season_tags={"autumn", "peak_season"},
        )
        list_user_trips.return_value = []
        list_plan_options.return_value = []
        list_sessions.return_value = []
        list_preferences.return_value = []
        add_history_recall_log.side_effect = lambda db, log: log

        service = RecallService(db=MagicMock())
        service.search_history(
            user_id=uuid.uuid4(),
            query_text="国庆去北京还有之前方案吗",
            session_id=uuid.uuid4(),
        )

        _, kwargs = build_query_profile.call_args
        self.assertEqual(resolve_holiday_window.return_value, kwargs["holiday_window"])

    @patch("services.recall_service.add_history_recall_log")
    @patch("services.recall_service.score_recall_candidate")
    @patch("services.recall_service.list_active_user_preferences")
    @patch("services.recall_service.list_user_sessions_for_recall")
    @patch("services.recall_service.list_user_plan_options_for_recall")
    @patch("services.recall_service.list_user_trips")
    def test_search_history_returns_grouped_matches_and_injection_section(
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
            title="成都亲子行程",
            primary_destination="成都",
            summary="成都亲子三日游",
            plan_markdown="成都亲子三日游详细安排",
            destinations=[SimpleNamespace(destination_name="成都")],
        )
        option = SimpleNamespace(
            id=uuid.uuid4(),
            title="成都备选方案",
            primary_destination="成都",
            summary="更偏美食和慢节奏",
            plan_markdown="成都慢节奏方案",
            preferences={"budget": {"level": "economy"}},
        )
        past_session = SimpleNamespace(
            id=uuid.uuid4(),
            title="成都聊天记录",
            summary="上次讨论过成都亲子路线",
            latest_user_message="想找成都亲子轻松一点的安排",
        )

        list_user_trips.return_value = [trip]
        list_plan_options.return_value = [option]
        list_sessions.return_value = [past_session]
        list_preferences.return_value = [build_preference()]

        def fake_score(*args, **kwargs):
            title = kwargs["candidate_texts"][0]
            if title == "成都亲子行程":
                return 0.91, ["目的地匹配:成都", "关键词重合:亲子"]
            if title == "成都备选方案":
                return 0.78, ["关键词重合:成都"]
            if title == "成都聊天记录":
                return 0.62, ["关键词重合:成都"]
            if title == "budget":
                return 0.72, ["偏好重合:budget.level"]
            return 0.20, []

        score_recall_candidate.side_effect = fake_score

        def keep_log(db, log):
            if log.id is None:
                log.id = uuid.uuid4()
            return log

        add_history_recall_log.side_effect = keep_log

        service = RecallService(db=MagicMock())
        result = service.search_history(
            user_id=user_id,
            query_text="还记得之前成都亲子且预算有限的安排吗",
            session_id=session_id,
        )

        self.assertIn("grouped_matches", result)
        self.assertIn("decision_groups", result)
        self.assertIn("decision_summary", result)
        self.assertTrue(result["grouped_matches"]["strong_history"])
        self.assertTrue(result["grouped_matches"]["candidate_options"])
        self.assertTrue(result["grouped_matches"]["relevant_preferences"])
        self.assertTrue(result["grouped_matches"]["related_sessions"])
        self.assertTrue(result["decision_groups"]["adoptable"])
        self.assertIn("强相关的正式行程 / 已成型历史方案", result["injection_section"])
        self.assertIn("命中的相关长期偏好", result["injection_section"])
        self.assertIn("若命中同一目的地、同一时间窗、同一偏好约束", result["injection_section"])

        recall_log = add_history_recall_log.call_args.args[1]
        self.assertIn("grouped_matches", recall_log.recall_payload)
        self.assertIn("decision_groups", recall_log.recall_payload)
        self.assertIn("decision_summary", recall_log.recall_payload)
        self.assertEqual(
            result["injection_section"],
            recall_log.recall_payload["injection_section"],
        )


if __name__ == "__main__":
    unittest.main()
