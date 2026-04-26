import unittest
import uuid
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "langchain_core.messages" not in sys.modules:
    langchain_core = types.ModuleType("langchain_core")
    messages_module = types.ModuleType("langchain_core.messages")
    tools_module = types.ModuleType("langchain_core.tools")

    class _Message:
        def __init__(self, content=None):
            self.content = content

    def tool(func=None, *args, **kwargs):
        if func is None:
            return lambda inner: inner
        return func

    messages_module.AIMessage = _Message
    messages_module.HumanMessage = _Message
    messages_module.SystemMessage = _Message
    tools_module.tool = tool
    langchain_core.messages = messages_module
    langchain_core.tools = tools_module
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.messages"] = messages_module
    sys.modules["langchain_core.tools"] = tools_module

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    httpx_module.get = MagicMock()
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

from db.models import ChatSession
from services.comparison_service import ComparisonService
from services.trip_service import TripService


def build_session() -> ChatSession:
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="状态治理测试工作区",
        status="active",
    )
    return session


class WorkspaceStateServiceTests(unittest.TestCase):
    @patch("services.comparison_service.create_session_event")
    @patch("services.comparison_service.add_plan_comparison_item")
    @patch("services.comparison_service.add_plan_comparison")
    @patch("services.comparison_service.get_active_comparison")
    def test_comparison_service_deduplicates_option_ids_and_carries_active_plan_as_recommendation(
        self,
        get_active_comparison,
        add_plan_comparison,
        add_plan_comparison_item,
        create_session_event,
    ):
        session = build_session()
        option_a_id = uuid.uuid4()
        option_b_id = uuid.uuid4()
        session.active_plan_option_id = option_a_id

        option_a = SimpleNamespace(id=option_a_id, title="北京方案", status="draft")
        option_b = SimpleNamespace(id=option_b_id, title="天津方案", status="draft")
        comparison = SimpleNamespace(
            id=uuid.uuid4(),
            name="",
            status="active",
            summary="",
            comparison_dimensions=[],
            recommended_option_id=None,
        )

        get_active_comparison.return_value = None
        add_plan_comparison.return_value = comparison

        service = ComparisonService(db=MagicMock())
        service.session_service = MagicMock()
        service.session_service.get_session_or_raise.return_value = session
        service.plan_option_service = MagicMock()
        service.plan_option_service.get_plan_option_or_raise.side_effect = [
            option_a,
            option_b,
        ]

        created = service.create_or_update_comparison(
            session_id=session.id,
            user_id=session.user_id,
            plan_option_ids=[option_a_id, option_a_id, option_b_id],
            commit=False,
        )

        self.assertEqual(2, service.plan_option_service.get_plan_option_or_raise.call_count)
        self.assertEqual(option_a_id, created.recommended_option_id)
        self.assertEqual(2, add_plan_comparison_item.call_count)
        event_payload = create_session_event.call_args.kwargs["event_payload"]
        self.assertEqual(str(option_a_id), event_payload["recommended_option_id"])
        self.assertEqual(str(created.id), event_payload["workspace_state"]["active_comparison_id"])

    @patch("services.comparison_service.create_session_event")
    @patch("services.comparison_service.add_plan_comparison_item")
    @patch("services.comparison_service.add_plan_comparison")
    @patch("services.comparison_service.get_active_comparison")
    def test_comparison_service_auto_recommends_richer_option_when_no_active_plan(
        self,
        get_active_comparison,
        add_plan_comparison,
        add_plan_comparison_item,
        create_session_event,
    ):
        session = build_session()
        option_a_id = uuid.uuid4()
        option_b_id = uuid.uuid4()

        option_a = SimpleNamespace(
            id=option_a_id,
            title="杭州简版",
            status="draft",
            summary="只保留景点概要",
            plan_markdown="西湖一日游",
            primary_destination="杭州",
            total_days=1,
            pace=None,
            budget_min=None,
            budget_max=None,
            constraints={},
        )
        option_b = SimpleNamespace(
            id=option_b_id,
            title="杭州完整方案",
            status="draft",
            summary="包含路线、住宿、美食与逐段交通",
            plan_markdown="Day1 西湖 -> 河坊街\nDay2 灵隐寺 -> 龙井\n附住宿和美食推荐",
            primary_destination="杭州",
            total_days=2,
            pace="relaxed",
            budget_min=300,
            budget_max=800,
            constraints={
                "structured_context": {
                    "amap": {
                        "cards": [
                            {"type": "route"},
                            {"type": "stay_recommendations"},
                            {"type": "food_recommendations"},
                        ],
                        "routes": [
                            {"legs": [{"segment_no": 1}]},
                        ],
                    }
                }
            },
        )
        comparison = SimpleNamespace(
            id=uuid.uuid4(),
            name="",
            status="active",
            summary="",
            comparison_dimensions=[],
            recommended_option_id=None,
        )

        get_active_comparison.return_value = None
        add_plan_comparison.return_value = comparison

        service = ComparisonService(db=MagicMock())
        service.session_service = MagicMock()
        service.session_service.get_session_or_raise.return_value = session
        service.plan_option_service = MagicMock()
        service.plan_option_service.get_plan_option_or_raise.side_effect = [
            option_a,
            option_b,
        ]

        created = service.create_or_update_comparison(
            session_id=session.id,
            user_id=session.user_id,
            plan_option_ids=[option_a_id, option_b_id],
            commit=False,
        )

        self.assertEqual(option_b_id, created.recommended_option_id)
        self.assertIn("当前推荐方案：杭州完整方案", created.summary)
        self.assertIn("地图结构化结果更完整", created.summary)
        self.assertIn("备选方案：杭州简版", created.summary)
        event_payload = create_session_event.call_args.kwargs["event_payload"]
        self.assertEqual(str(option_b_id), event_payload["recommended_option_id"])
        self.assertTrue(event_payload["recommendation_reasons"])

    def test_comparison_service_builds_structured_decision_payload(self):
        option_a_id = uuid.uuid4()
        option_b_id = uuid.uuid4()
        comparison = SimpleNamespace(
            recommended_option_id=option_b_id,
            recommended_option=SimpleNamespace(title="杭州完整方案"),
            summary=(
                "系统已自动比较 2 个候选方案：杭州简版、杭州完整方案。\n"
                "当前推荐方案：杭州完整方案。\n"
                "推荐理由：地图结构化结果更完整；已包含住宿推荐；已包含景点间逐段交通。\n"
                "备选方案：杭州简版。"
            ),
            items=[
                SimpleNamespace(plan_option=SimpleNamespace(id=option_a_id, title="杭州简版")),
                SimpleNamespace(plan_option=SimpleNamespace(id=option_b_id, title="杭州完整方案")),
            ],
        )

        payload = ComparisonService.build_decision_payload(comparison)

        self.assertEqual(str(option_b_id), payload["recommended_plan_option_id"])
        self.assertEqual("杭州完整方案", payload["recommended_plan_title"])
        self.assertEqual(["杭州简版"], payload["alternate_plan_titles"])
        self.assertEqual(
            ["地图结构化结果更完整", "已包含住宿推荐", "已包含景点间逐段交通"],
            payload["recommendation_reasons"],
        )

    @patch("services.trip_service.get_plan_option")
    @patch("services.trip_service.get_plan_comparison")
    def test_trip_service_uses_active_comparison_when_request_omits_comparison_id(
        self,
        get_plan_comparison,
        get_plan_option,
    ):
        session = build_session()
        comparison_id = uuid.uuid4()
        option_id = uuid.uuid4()
        session.active_comparison_id = comparison_id
        session.active_plan_option_id = option_id

        comparison = SimpleNamespace(
            id=comparison_id,
            recommended_option_id=option_id,
            status="active",
        )
        plan_option = SimpleNamespace(id=option_id)
        get_plan_comparison.return_value = comparison
        get_plan_option.return_value = plan_option

        service = TripService(db=MagicMock())
        service.session_service = MagicMock()
        service.session_service.get_session_or_raise.return_value = session
        service._create_trip_from_plan_option = MagicMock(return_value="trip")

        result = service.create_trip(
            session_id=session.id,
            user_id=session.user_id,
            plan_option_id=None,
            comparison_id=None,
            commit=False,
        )

        self.assertEqual("trip", result)
        get_plan_comparison.assert_called_once()
        kwargs = service._create_trip_from_plan_option.call_args.kwargs
        self.assertEqual(comparison, kwargs["comparison"])
        self.assertEqual("comparison_recommended", kwargs["selection_source"])

    @patch("services.trip_service.get_latest_session_trip")
    @patch("services.trip_service.get_latest_trip_for_plan_option")
    @patch("services.trip_service.get_plan_option")
    def test_sync_trip_prefers_updating_latest_session_trip_when_recommended_plan_changes(
        self,
        get_plan_option,
        get_latest_trip_for_plan_option,
        get_latest_session_trip,
    ):
        session = build_session()
        target_option_id = uuid.uuid4()
        target_plan_option = SimpleNamespace(id=target_option_id)
        existing_trip = SimpleNamespace(id=uuid.uuid4(), source_plan_option_id=uuid.uuid4())

        get_plan_option.return_value = target_plan_option
        get_latest_trip_for_plan_option.return_value = None
        get_latest_session_trip.return_value = existing_trip

        service = TripService(db=MagicMock())
        service.session_service = MagicMock()
        service.session_service.get_session_or_raise.return_value = session
        service._update_trip_from_plan_option = MagicMock(return_value="updated-trip")

        result = service.sync_trip_from_plan_option(
            session_id=session.id,
            user_id=session.user_id,
            plan_option_id=target_option_id,
            comparison_id=None,
            commit=False,
        )

        self.assertEqual("updated-trip", result)
        get_latest_trip_for_plan_option.assert_called_once_with(
            service.db,
            session_id=session.id,
            plan_option_id=target_option_id,
            user_id=session.user_id,
        )
        get_latest_session_trip.assert_called_once_with(
            service.db,
            session_id=session.id,
            user_id=session.user_id,
        )
        update_kwargs = service._update_trip_from_plan_option.call_args.kwargs
        self.assertIs(existing_trip, update_kwargs["trip"])
        self.assertIs(target_plan_option, update_kwargs["plan_option"])

    @patch("services.trip_service.create_session_event")
    @patch("services.trip_service.add_trip_itinerary_day")
    @patch("services.trip_service.add_trip_destination")
    @patch("services.trip_service.add_trip")
    @patch("services.trip_service.get_latest_assistant_message")
    def test_trip_service_carries_structured_amap_context_into_trip_and_itinerary(
        self,
        get_latest_assistant_message,
        add_trip,
        add_trip_destination,
        add_trip_itinerary_day,
        create_session_event,
    ):
        session = build_session()
        plan_option = SimpleNamespace(
            id=uuid.uuid4(),
            title="杭州两日慢游",
            primary_destination="杭州",
            travel_start_date=None,
            travel_end_date=None,
            total_days=2,
            traveler_profile={},
            budget_min=None,
            budget_max=None,
            pace=None,
            preferences={},
            constraints={},
            summary="围绕西湖与河坊街安排两天行程。",
            plan_markdown="## 杭州两日慢游\n先逛西湖，再去河坊街。",
            destinations=[],
            is_selected=False,
            status="draft",
        )
        latest_assistant = SimpleNamespace(
            id=uuid.uuid4(),
            content="\n".join(
                [
                    "## 推荐方案",
                    "### 预算汇总",
                    "- 人均约 1200-1600 元，含酒店与市内交通",
                    "- 酒店预算：500-700 元/晚",
                    "### 注意事项",
                    "- 西湖和河坊街周边节假日人流较大，建议早点出发",
                    "- 晚间回酒店尽量避开末班车前高峰",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 跨城到达建议（12306预留）",
                            "- 出发城市：上海",
                            "- 目的城市：杭州",
                            "- 出发日期：2026-05-01",
                            "- 推荐方式：高铁/动车（12306待接入）",
                            "- 预计耗时：待接入12306后补全",
                            "- 票价参考：待接入12306后补全",
                            "- 接入状态：placeholder",
                            "- 方案摘要：建议优先高铁到达杭州东站，再衔接西湖片区酒店。",
                            "",
                            "### 补充说明",
                            "- 当前为 12306 预留接口，暂未接入真实车次。",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 路线规划",
                            "- 起点：杭州东站",
                            "- 终点：西湖",
                            "- 出行方式：公交/地铁",
                            "- 城市：杭州",
                            "距离：8.2 km",
                            "预计耗时：24分钟",
                            "总步行距离：450 米",
                            "票价参考：3 元",
                            "",
                            "### 逐步换乘",
                            "1. 步行 300 米到龙翔桥站",
                            "   - 类型：步行",
                            "   - 距离：300 米",
                            "   - 到达点：龙翔桥站",
                            "2. 乘坐 地铁1号线，从龙翔桥站到定安路站，经过 2 站",
                            "   - 类型：地铁",
                            "   - 线路：地铁1号线",
                            "   - 上车站：龙翔桥站",
                            "   - 下车站：定安路站",
                            "   - 站数：2",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 住宿推荐（酒店/民宿）",
                            "- 中心点：西湖",
                            "- 检索半径：5000 米",
                            "- 筛选后数量：1/4",
                            "- 筛选条件：预算≤400 元，评分≥4.5，距离≤3000 米",
                            "",
                            "### 推荐列表",
                            "1. **湖畔酒店**（酒店）",
                            "   距离：900 m｜评分：4.8｜人均：380 元",
                            "   地址：西湖大道 1 号｜电话：0571-12345678",
                        ]
                    ),
                ]
            },
        )
        get_latest_assistant_message.return_value = latest_assistant

        created_trip = {}

        def add_trip_side_effect(db, trip):
            trip.id = uuid.uuid4()
            trip.destinations = []
            trip.itinerary_days = []
            created_trip["trip"] = trip
            return trip

        add_trip.side_effect = add_trip_side_effect

        def add_trip_destination_side_effect(db, destination):
            created_trip["trip"].destinations.append(destination)
            return destination

        add_trip_destination.side_effect = add_trip_destination_side_effect

        captured_days = []

        def add_trip_itinerary_day_side_effect(db, itinerary_day):
            captured_days.append(itinerary_day)
            created_trip["trip"].itinerary_days.append(itinerary_day)
            return itinerary_day

        add_trip_itinerary_day.side_effect = add_trip_itinerary_day_side_effect

        service = TripService(db=MagicMock())
        trip = service._create_trip_from_plan_option(
            session=session,
            user_id=session.user_id,
            plan_option=plan_option,
            comparison=None,
            selection_source="active_session_plan_option",
            commit=False,
        )

        self.assertIs(trip, created_trip["trip"])
        structured_context = trip.constraints["structured_context"]
        self.assertIn("amap", structured_context)
        self.assertIn("railway12306", structured_context)
        self.assertIn("assistant_plan", structured_context)
        self.assertEqual("route", structured_context["amap"]["cards"][0]["type"])
        self.assertEqual(
            "arrival_recommendation",
            structured_context["railway12306"]["cards"][0]["type"],
        )
        self.assertEqual(
            "budget_summary",
            structured_context["assistant_plan"]["cards"][0]["type"],
        )
        self.assertEqual(
            str(latest_assistant.id),
            structured_context["amap"]["source_message_id"],
        )
        self.assertEqual(structured_context, plan_option.constraints["structured_context"])
        self.assertEqual(2, len(captured_days))
        self.assertEqual(4, len(captured_days[0].items))
        self.assertEqual("当日景点动线：杭州东站 -> 西湖", captured_days[0].summary)
        self.assertEqual("route", captured_days[0].items[0]["type"])
        self.assertEqual("stay_recommendations", captured_days[0].items[1]["type"])
        self.assertEqual("arrival_recommendation", captured_days[0].items[2]["type"])
        self.assertEqual("transit", captured_days[0].items[3]["type"])
        self.assertEqual("morning", captured_days[0].items[2]["time_period"])
        self.assertEqual("morning", captured_days[0].items[3]["time_period"])
        self.assertEqual("杭州东站", captured_days[0].items[3]["from"])
        self.assertEqual("西湖", captured_days[0].items[3]["to"])
        self.assertEqual(
            [
                "步行 300 米到龙翔桥站",
                "乘坐 地铁1号线，从龙翔桥站到定安路站，经过 2 站",
            ],
            captured_days[0].items[3]["steps"],
        )
        self.assertEqual("budget_summary", captured_days[1].items[0]["type"])
        self.assertEqual("travel_notes", captured_days[1].items[1]["type"])
        self.assertEqual("evening", captured_days[1].items[0]["time_period"])
        self.assertEqual("evening", captured_days[1].items[1]["time_period"])
        self.assertTrue(create_session_event.called)

    def test_trip_service_splits_spot_route_items_across_multiple_days(self):
        structured_context = {
            "amap": {
                "cards": [
                    {
                        "provider": "amap",
                        "type": "spot_route",
                        "title": "景点串联路线",
                        "summary": "杭州公交/地铁串联 3 个点位",
                        "data": {"spot_sequence": ["西湖", "河坊街", "南宋御街"]},
                    },
                    {
                        "provider": "amap",
                        "type": "stay_recommendations",
                        "title": "住宿推荐",
                        "summary": "西湖附近住宿",
                        "data": {"center": "西湖"},
                    },
                    {
                        "provider": "amap",
                        "type": "food_recommendations",
                        "title": "周边美食推荐",
                        "summary": "河坊街附近美食",
                        "data": {"center": "河坊街"},
                    },
                    {
                        "provider": "amap",
                        "type": "poi_list",
                        "title": "POI 候选点位",
                        "summary": "南宋御街候选点位",
                        "data": {"city": "杭州"},
                    },
                ],
                "routes": [
                    {
                        "route_kind": "spot_sequence",
                        "city": "杭州",
                        "mode": "公交/地铁",
                        "spot_sequence": ["西湖", "河坊街", "南宋御街"],
                        "original_spot_sequence": ["西湖", "南宋御街", "河坊街"],
                        "optimization_note": "已启用（固定首点：西湖）",
                        "legs": [
                            {
                                "segment_no": 1,
                                "origin": "西湖",
                                "destination": "河坊街",
                                "duration_text": "24分钟",
                                "steps": [
                                    {"instruction": "步行 300 米到龙翔桥站"},
                                    {"instruction": "乘坐 地铁1号线，从龙翔桥站到定安路站，经过 2 站"},
                                ],
                            },
                            {
                                "segment_no": 2,
                                "origin": "河坊街",
                                "destination": "南宋御街",
                                "duration_text": "12分钟",
                                "steps": [
                                    {"instruction": "步行 800 米到南宋御街"},
                                ],
                            },
                        ],
                    }
                ],
            }
        }

        items_by_day = TripService._build_itinerary_items_by_day(
            structured_context=structured_context,
            total_days=2,
        )

        self.assertEqual(2, len(items_by_day))
        self.assertEqual("spot_route", items_by_day[0][0]["type"])
        self.assertEqual("stay_recommendations", items_by_day[0][1]["type"])
        self.assertEqual("spot_sequence", items_by_day[0][2]["type"])
        self.assertEqual("transit", items_by_day[0][3]["type"])
        self.assertEqual("morning", items_by_day[0][0]["time_period"])
        self.assertEqual("evening", items_by_day[0][1]["time_period"])
        self.assertEqual("morning", items_by_day[0][2]["time_period"])
        self.assertEqual("morning", items_by_day[0][3]["time_period"])
        self.assertEqual("西湖", items_by_day[0][3]["from"])
        day_payloads = TripService._build_itinerary_days_payload(
            structured_context=structured_context,
            total_days=2,
        )
        self.assertEqual("当日景点动线：西湖 -> 河坊街", day_payloads[0]["summary"])
        self.assertEqual("当日景点动线：河坊街 -> 南宋御街", day_payloads[1]["summary"])
        self.assertEqual("河坊街", items_by_day[1][0]["from"])
        self.assertEqual("morning", items_by_day[1][0]["time_period"])
        self.assertEqual("food_recommendations", items_by_day[1][1]["type"])
        self.assertEqual("afternoon", items_by_day[1][1]["time_period"])
        self.assertEqual("poi_list", items_by_day[1][2]["type"])
        self.assertEqual("afternoon", items_by_day[1][2]["time_period"])


if __name__ == "__main__":
    unittest.main()
