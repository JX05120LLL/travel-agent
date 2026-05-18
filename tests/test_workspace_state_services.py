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
from services.travel.comparison_service import ComparisonService
from services.travel.trip_service import TripService


def build_session() -> ChatSession:
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="鐘舵€佹不鐞嗘祴璇曞伐浣滃尯",
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

        option_a = SimpleNamespace(id=option_a_id, title="鍖椾含鏂规", status="draft")
        option_b = SimpleNamespace(id=option_b_id, title="澶╂触鏂规", status="draft")
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
            title="鏉窞绠€鐗?,
            status="draft",
            summary="鍙繚鐣欐櫙鐐规瑕?,
            plan_markdown="瑗挎箹涓€鏃ユ父",
            primary_destination="鏉窞",
            total_days=1,
            pace=None,
            budget_min=None,
            budget_max=None,
            constraints={},
        )
        option_b = SimpleNamespace(
            id=option_b_id,
            title="鏉窞瀹屾暣鏂规",
            status="draft",
            summary="鍖呭惈璺嚎銆佷綇瀹裤€佺編椋熶笌閫愭浜ら€?,
            plan_markdown="Day1 瑗挎箹 -> 娌冲潑琛梊nDay2 鐏甸殣瀵?-> 榫欎簳\n闄勪綇瀹垮拰缇庨鎺ㄨ崘",
            primary_destination="鏉窞",
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
        self.assertIn("褰撳墠鎺ㄨ崘鏂规锛氭澀宸炲畬鏁存柟妗?, created.summary)
        self.assertIn("鍦板浘缁撴瀯鍖栫粨鏋滄洿瀹屾暣", created.summary)
        self.assertIn("澶囬€夋柟妗堬細鏉窞绠€鐗?, created.summary)
        event_payload = create_session_event.call_args.kwargs["event_payload"]
        self.assertEqual(str(option_b_id), event_payload["recommended_option_id"])
        self.assertTrue(event_payload["recommendation_reasons"])

    def test_comparison_service_builds_structured_decision_payload(self):
        option_a_id = uuid.uuid4()
        option_b_id = uuid.uuid4()
        comparison = SimpleNamespace(
            recommended_option_id=option_b_id,
            recommended_option=SimpleNamespace(title="鏉窞瀹屾暣鏂规"),
            summary=(
                "绯荤粺宸茶嚜鍔ㄦ瘮杈?2 涓€欓€夋柟妗堬細鏉窞绠€鐗堛€佹澀宸炲畬鏁存柟妗堛€俓n"
                "褰撳墠鎺ㄨ崘鏂规锛氭澀宸炲畬鏁存柟妗堛€俓n"
                "鎺ㄨ崘鐞嗙敱锛氬湴鍥剧粨鏋勫寲缁撴灉鏇村畬鏁达紱宸插寘鍚綇瀹挎帹鑽愶紱宸插寘鍚櫙鐐归棿閫愭浜ら€氥€俓n"
                "澶囬€夋柟妗堬細鏉窞绠€鐗堛€?
            ),
            items=[
                SimpleNamespace(plan_option=SimpleNamespace(id=option_a_id, title="鏉窞绠€鐗?)),
                SimpleNamespace(plan_option=SimpleNamespace(id=option_b_id, title="鏉窞瀹屾暣鏂规")),
            ],
        )

        payload = ComparisonService.build_decision_payload(comparison)

        self.assertEqual(str(option_b_id), payload["recommended_plan_option_id"])
        self.assertEqual("鏉窞瀹屾暣鏂规", payload["recommended_plan_title"])
        self.assertEqual(["鏉窞绠€鐗?], payload["alternate_plan_titles"])
        self.assertEqual(
            ["鍦板浘缁撴瀯鍖栫粨鏋滄洿瀹屾暣", "宸插寘鍚綇瀹挎帹鑽?, "宸插寘鍚櫙鐐归棿閫愭浜ら€?],
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
            title="鏉窞涓ゆ棩鎱㈡父",
            primary_destination="鏉窞",
            travel_start_date=None,
            travel_end_date=None,
            total_days=2,
            traveler_profile={},
            budget_min=None,
            budget_max=None,
            pace=None,
            preferences={},
            constraints={},
            summary="鍥寸粫瑗挎箹涓庢渤鍧婅瀹夋帓涓ゅぉ琛岀▼銆?,
            plan_markdown="## 鏉窞涓ゆ棩鎱㈡父\n鍏堥€涜タ婀栵紝鍐嶅幓娌冲潑琛椼€?,
            destinations=[],
            is_selected=False,
            status="draft",
        )
        latest_assistant = SimpleNamespace(
            id=uuid.uuid4(),
            content="\n".join(
                [
                    "## 鎺ㄨ崘鏂规",
                    "### 棰勭畻姹囨€?,
                    "- 浜哄潎绾?1200-1600 鍏冿紝鍚厭搴椾笌甯傚唴浜ら€?,
                    "- 閰掑簵棰勭畻锛?00-700 鍏?鏅?,
                    "### 娉ㄦ剰浜嬮」",
                    "- 瑗挎箹鍜屾渤鍧婅鍛ㄨ竟鑺傚亣鏃ヤ汉娴佽緝澶э紝寤鸿鏃╃偣鍑哄彂",
                    "- 鏅氶棿鍥為厭搴楀敖閲忛伩寮€鏈彮杞﹀墠楂樺嘲",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 璺ㄥ煄鍒拌揪寤鸿锛?2306棰勭暀锛?,
                            "- 鍑哄彂鍩庡競锛氫笂娴?,
                            "- 鐩殑鍩庡競锛氭澀宸?,
                            "- 鍑哄彂鏃ユ湡锛?026-05-01",
                            "- 鎺ㄨ崘鏂瑰紡锛氶珮閾?鍔ㄨ溅锛?2306寰呮帴鍏ワ級",
                            "- 棰勮鑰楁椂锛氬緟鎺ュ叆12306鍚庤ˉ鍏?,
                            "- 绁ㄤ环鍙傝€冿細寰呮帴鍏?2306鍚庤ˉ鍏?,
                            "- 鎺ュ叆鐘舵€侊細placeholder",
                            "- 鏂规鎽樿锛氬缓璁紭鍏堥珮閾佸埌杈炬澀宸炰笢绔欙紝鍐嶈鎺ヨタ婀栫墖鍖洪厭搴椼€?,
                            "",
                            "### 琛ュ厖璇存槑",
                            "- 褰撳墠涓?12306 棰勭暀鎺ュ彛锛屾殏鏈帴鍏ョ湡瀹炶溅娆°€?,
                        ]
                    ),
                    "\n".join(
                        [
                            "## 璺嚎瑙勫垝",
                            "- 璧风偣锛氭澀宸炰笢绔?,
                            "- 缁堢偣锛氳タ婀?,
                            "- 鍑鸿鏂瑰紡锛氬叕浜?鍦伴搧",
                            "- 鍩庡競锛氭澀宸?,
                            "璺濈锛?.2 km",
                            "棰勮鑰楁椂锛?4鍒嗛挓",
                            "鎬绘琛岃窛绂伙細450 绫?,
                            "绁ㄤ环鍙傝€冿細3 鍏?,
                            "",
                            "### 閫愭鎹箻",
                            "1. 姝ヨ 300 绫冲埌榫欑繑妗ョ珯",
                            "   - 绫诲瀷锛氭琛?,
                            "   - 璺濈锛?00 绫?,
                            "   - 鍒拌揪鐐癸細榫欑繑妗ョ珯",
                            "2. 涔樺潗 鍦伴搧1鍙风嚎锛屼粠榫欑繑妗ョ珯鍒板畾瀹夎矾绔欙紝缁忚繃 2 绔?,
                            "   - 绫诲瀷锛氬湴閾?,
                            "   - 绾胯矾锛氬湴閾?鍙风嚎",
                            "   - 涓婅溅绔欙細榫欑繑妗ョ珯",
                            "   - 涓嬭溅绔欙細瀹氬畨璺珯",
                            "   - 绔欐暟锛?",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 浣忓鎺ㄨ崘锛堥厭搴?姘戝锛?,
                            "- 涓績鐐癸細瑗挎箹",
                            "- 妫€绱㈠崐寰勶細5000 绫?,
                            "- 绛涢€夊悗鏁伴噺锛?/4",
                            "- 绛涢€夋潯浠讹細棰勭畻鈮?00 鍏冿紝璇勫垎鈮?.5锛岃窛绂烩墹3000 绫?,
                            "",
                            "### 鎺ㄨ崘鍒楄〃",
                            "1. **婀栫晹閰掑簵**锛堥厭搴楋級",
                            "   璺濈锛?00 m锝滆瘎鍒嗭細4.8锝滀汉鍧囷細380 鍏?,
                            "   鍦板潃锛氳タ婀栧ぇ閬?1 鍙凤綔鐢佃瘽锛?571-12345678",
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
        self.assertEqual("褰撴棩鏅偣鍔ㄧ嚎锛氭澀宸炰笢绔?-> 瑗挎箹", captured_days[0].summary)
        self.assertEqual("route", captured_days[0].items[0]["type"])
        self.assertEqual("stay_recommendations", captured_days[0].items[1]["type"])
        self.assertEqual("arrival_recommendation", captured_days[0].items[2]["type"])
        self.assertEqual("transit", captured_days[0].items[3]["type"])
        self.assertEqual("morning", captured_days[0].items[2]["time_period"])
        self.assertEqual("morning", captured_days[0].items[3]["time_period"])
        self.assertEqual("鏉窞涓滅珯", captured_days[0].items[3]["from"])
        self.assertEqual("瑗挎箹", captured_days[0].items[3]["to"])
        self.assertEqual(
            [
                "姝ヨ 300 绫冲埌榫欑繑妗ョ珯",
                "涔樺潗 鍦伴搧1鍙风嚎锛屼粠榫欑繑妗ョ珯鍒板畾瀹夎矾绔欙紝缁忚繃 2 绔?,
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
                        "title": "鏅偣涓茶仈璺嚎",
                        "summary": "鏉窞鍏氦/鍦伴搧涓茶仈 3 涓偣浣?,
                        "data": {"spot_sequence": ["瑗挎箹", "娌冲潑琛?, "鍗楀畫寰¤"]},
                    },
                    {
                        "provider": "amap",
                        "type": "stay_recommendations",
                        "title": "浣忓鎺ㄨ崘",
                        "summary": "瑗挎箹闄勮繎浣忓",
                        "data": {"center": "瑗挎箹"},
                    },
                    {
                        "provider": "amap",
                        "type": "food_recommendations",
                        "title": "鍛ㄨ竟缇庨鎺ㄨ崘",
                        "summary": "娌冲潑琛楅檮杩戠編椋?,
                        "data": {"center": "娌冲潑琛?},
                    },
                    {
                        "provider": "amap",
                        "type": "poi_list",
                        "title": "POI 鍊欓€夌偣浣?,
                        "summary": "鍗楀畫寰¤鍊欓€夌偣浣?,
                        "data": {"city": "鏉窞"},
                    },
                ],
                "routes": [
                    {
                        "route_kind": "spot_sequence",
                        "city": "鏉窞",
                        "mode": "鍏氦/鍦伴搧",
                        "spot_sequence": ["瑗挎箹", "娌冲潑琛?, "鍗楀畫寰¤"],
                        "original_spot_sequence": ["瑗挎箹", "鍗楀畫寰¤", "娌冲潑琛?],
                        "optimization_note": "宸插惎鐢紙鍥哄畾棣栫偣锛氳タ婀栵級",
                        "legs": [
                            {
                                "segment_no": 1,
                                "origin": "瑗挎箹",
                                "destination": "娌冲潑琛?,
                                "duration_text": "24鍒嗛挓",
                                "steps": [
                                    {"instruction": "姝ヨ 300 绫冲埌榫欑繑妗ョ珯"},
                                    {"instruction": "涔樺潗 鍦伴搧1鍙风嚎锛屼粠榫欑繑妗ョ珯鍒板畾瀹夎矾绔欙紝缁忚繃 2 绔?},
                                ],
                            },
                            {
                                "segment_no": 2,
                                "origin": "娌冲潑琛?,
                                "destination": "鍗楀畫寰¤",
                                "duration_text": "12鍒嗛挓",
                                "steps": [
                                    {"instruction": "姝ヨ 800 绫冲埌鍗楀畫寰¤"},
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
        self.assertEqual("瑗挎箹", items_by_day[0][3]["from"])
        day_payloads = TripService._build_itinerary_days_payload(
            structured_context=structured_context,
            total_days=2,
        )
        self.assertEqual("褰撴棩鏅偣鍔ㄧ嚎锛氳タ婀?-> 娌冲潑琛?, day_payloads[0]["summary"])
        self.assertEqual("褰撴棩鏅偣鍔ㄧ嚎锛氭渤鍧婅 -> 鍗楀畫寰¤", day_payloads[1]["summary"])
        self.assertEqual("娌冲潑琛?, items_by_day[1][0]["from"])
        self.assertEqual("morning", items_by_day[1][0]["time_period"])
        self.assertEqual("food_recommendations", items_by_day[1][1]["type"])
        self.assertEqual("afternoon", items_by_day[1][1]["time_period"])
        self.assertEqual("poi_list", items_by_day[1][2]["type"])
        self.assertEqual("afternoon", items_by_day[1][2]["time_period"])


if __name__ == "__main__":
    unittest.main()
