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
from services.chat.recall_service import RecallService


def build_preference() -> UserPreference:
    preference = UserPreference(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        preference_category="budget",
        preference_key="level",
        preference_value={"value": "economy", "label": "棰勭畻鍋忕粡娴?, "evidence": "棰勭畻鏈夐檺"},
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
            "holiday_name": "鍥藉簡鑺?,
            "start_date": "2026-10-01",
            "end_date": "2026-10-07",
            "off_day_ranges": [("2026-10-01", "2026-10-07")],
        }
        build_query_profile.return_value = SimpleNamespace(
            cleaned_query="鍥藉簡鍖椾含",
            query_tokens={"鍥藉簡", "鍖椾含"},
            destinations=["鍖椾含"],
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
            query_text="鍥藉簡鍘诲寳浜繕鏈変箣鍓嶆柟妗堝悧",
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
            title="鎴愰兘浜插瓙琛岀▼",
            primary_destination="鎴愰兘",
            summary="鎴愰兘浜插瓙涓夋棩娓?,
            plan_markdown="鎴愰兘浜插瓙涓夋棩娓歌缁嗗畨鎺?,
            destinations=[SimpleNamespace(destination_name="鎴愰兘")],
        )
        option = SimpleNamespace(
            id=uuid.uuid4(),
            title="鎴愰兘澶囬€夋柟妗?,
            primary_destination="鎴愰兘",
            summary="鏇村亸缇庨鍜屾參鑺傚",
            plan_markdown="鎴愰兘鎱㈣妭濂忔柟妗?,
            preferences={"budget": {"level": "economy"}},
        )
        past_session = SimpleNamespace(
            id=uuid.uuid4(),
            title="鎴愰兘鑱婂ぉ璁板綍",
            summary="涓婃璁ㄨ杩囨垚閮戒翰瀛愯矾绾?,
            latest_user_message="鎯虫壘鎴愰兘浜插瓙杞绘澗涓€鐐圭殑瀹夋帓",
        )

        list_user_trips.return_value = [trip]
        list_plan_options.return_value = [option]
        list_sessions.return_value = [past_session]
        list_preferences.return_value = [build_preference()]

        def fake_score(*args, **kwargs):
            title = kwargs["candidate_texts"][0]
            if title == "鎴愰兘浜插瓙琛岀▼":
                return 0.91, ["鐩殑鍦板尮閰?鎴愰兘", "鍏抽敭璇嶉噸鍚?浜插瓙"]
            if title == "鎴愰兘澶囬€夋柟妗?:
                return 0.78, ["鍏抽敭璇嶉噸鍚?鎴愰兘"]
            if title == "鎴愰兘鑱婂ぉ璁板綍":
                return 0.62, ["鍏抽敭璇嶉噸鍚?鎴愰兘"]
            if title == "budget":
                return 0.72, ["鍋忓ソ閲嶅悎:budget.level"]
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
            query_text="杩樿寰椾箣鍓嶆垚閮戒翰瀛愪笖棰勭畻鏈夐檺鐨勫畨鎺掑悧",
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
        self.assertIn("寮虹浉鍏崇殑姝ｅ紡琛岀▼ / 宸叉垚鍨嬪巻鍙叉柟妗?, result["injection_section"])
        self.assertIn("鍛戒腑鐨勭浉鍏抽暱鏈熷亸濂?, result["injection_section"])
        self.assertIn("鑻ュ懡涓悓涓€鐩殑鍦般€佸悓涓€鏃堕棿绐椼€佸悓涓€鍋忓ソ绾︽潫", result["injection_section"])

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
