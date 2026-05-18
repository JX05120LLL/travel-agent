import sys
import types
import unittest
import uuid
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
    httpx_module.get = object
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

from db.models import ChatSession
from services.travel.trip_service import TripService


def build_session() -> ChatSession:
    return ChatSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="鏉窞涓ゅぉ鏃呰宸ヤ綔鍖?,
        status="active",
    )


class AgentEndToEndSmokeTests(unittest.TestCase):
    @patch("services.trip_service.create_session_event")
    @patch("services.trip_service.add_trip_itinerary_day")
    @patch("services.trip_service.add_trip_destination")
    @patch("services.trip_service.add_trip")
    @patch("services.trip_service.get_latest_assistant_message")
    def test_realistic_user_request_builds_one_stop_trip_payload(
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
            title="鏉窞涓ゅぉ杞绘澗娓?,
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
            summary="鍖呭惈鍒拌揪鏂瑰紡銆侀厭搴椼€佹櫙鐐逛覆鑱斾氦閫氥€佺編椋熶笌棰勭畻鎻愰啋銆?,
            plan_markdown="## 鏉窞涓ゅぉ杞绘澗娓竆n鍥寸粫瑗挎箹銆佹渤鍧婅涓庡崡瀹嬪尽琛楀畨鎺掍袱澶╄绋嬨€?,
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
                    "- 浜哄潎绾?1500-1900 鍏冿紝鍚線杩旈珮閾併€侀厭搴椾笌甯傚唴閫氬嫟",
                    "- 閰掑簵寤鸿鎺у埗鍦?500-700 鍏?鏅?,
                    "### 娉ㄦ剰浜嬮」",
                    "- 瑗挎箹涓庢渤鍧婅鑺傚亣鏃ヤ汉娴佽緝澶э紝寤鸿涓婂崍浼樺厛瀹夋帓鎴峰鏅偣",
                    "- 澶滈棿杩旈厭搴楀敖閲忛伩寮€鍦伴搧鏈彮杞﹀墠楂樺嘲",
                    "### 鏈鍋囪",
                    "- 榛樿浠庝笂娴峰嚭鍙戯紝娓哥帺 2 澶?1 鏅?,
                    "- 榛樿鏇村亸杞绘澗鑺傚锛屼紭鍏堟琛屼笌鍦伴搧鎺ラ┏",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 璺ㄥ煄鍒拌揪寤鸿锛?2306锛?,
                            "- 鍑哄彂鍩庡競锛氫笂娴?,
                            "- 鐩殑鍩庡競锛氭澀宸?,
                            "- 鍑哄彂鏃ユ湡锛?026-05-01",
                            "- 鎺ㄨ崘鏂瑰紡锛氶珮閾?鍔ㄨ溅锛堝緟纭杞︽锛?,
                            "- 棰勮鑰楁椂锛?灏忔椂08鍒嗛挓",
                            "- 绁ㄤ环鍙傝€冿細73 鍏冭捣",
                            "- 鎺ュ叆鐘舵€侊細placeholder",
                            "- 绁ㄥ姟鐘舵€侊細reference",
                            "- 鏁版嵁鏉ユ簮锛歱laceholder",
                            "- 鏂规鎽樿锛氬缓璁紭鍏堥珮閾佸埌杈炬澀宸炰笢绔欙紝鍐嶆崲涔樺湴閾佸墠寰€瑗挎箹鐗囧尯閰掑簵銆?,
                            "",
                            "### 鎺ㄨ崘杞︽",
                            "1. G7311",
                            "   - 绔欑偣锛氫笂娴疯櫣妗?-> 鏉窞涓?,
                            "   - 淇℃伅锛?7:00锝?8:08锝?灏忔椂08鍒嗛挓锝?3 鍏冭捣",
                            "",
                            "### 瀹樻柟璐エ鎻愰啋",
                            "- 娓犻亾锛氶搧璺?2306瀹樻柟",
                            "- 瀹樼綉锛歨ttps://www.12306.cn/",
                            "- App锛歨ttps://kyfw.12306.cn/otn/appDownload/init",
                            "- 鎻愰啋锛氳溅娆°€佺エ浠枫€佷綑绁ㄤ笌璐エ瑙勫垯璇蜂互閾佽矾12306瀹樼綉/App涓哄噯銆?,
                            "",
                            "### 琛ュ厖璇存槑",
                            "- 褰撳墠杞︽浠呬綔鏌ヨ鍙傝€冿紝璇峰墠寰€閾佽矾12306瀹樻柟瀹屾垚璐エ銆?,
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
                            "- 鎼滅储鍗婂緞锛?000 绫?,
                            "- 绛涢€夊悗鏁伴噺锛?/4",
                            "- 绛涢€夋潯浠讹細棰勭畻鈮?00 鍏冿紝璇勫垎鈮?.5锛岃窛绂烩墹3000 绫?,
                            "",
                            "### 鎺ㄨ崘鍒楄〃",
                            "1. **婀栫晹閰掑簵**锛堥厭搴楋級",
                            "   璺濈锛?00 m锝滆瘎鍒嗭細4.8锝滀汉鍧囷細580 鍏?,
                            "   鍦板潃锛氳タ婀栧ぇ閬?1 鍙凤綔鐢佃瘽锛?571-12345678",
                            "   浠锋牸鏉ユ簮锛氭渶浣庝环",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 閰掑簵姘戝鎺ㄨ崘锛堜緵搴斿晢鑱氬悎锛?,
                            "- 鐩殑鍦帮細鏉窞",
                            "- 涓績鐐癸細瑗挎箹",
                            "- 鎼滅储鍗婂緞锛?000 绫?,
                            "- 鎺ㄨ崘鏉ユ簮锛歛map_fallback",
                            "- 浠锋牸鐘舵€侊細reference",
                            "- 鍏ヤ綇鏃ユ湡锛?026-05-01",
                            "- 绂诲簵鏃ユ湡锛?026-05-02",
                            "",
                            "### 鎺ㄨ崘鍒楄〃",
                            "1. **婀栫晹閰掑簵**锛堥厭搴楋級",
                            "   - 鐗囧尯锛氳タ婀?,
                            "   - 璺濈锛?00 m",
                            "   - 璇勫垎锛?.8",
                            "   - 浠锋牸锛?80 鍏?鏅氳捣",
                            "   - 浠锋牸鏉ユ簮锛歛map_cost",
                            "   - 鏄惁瀹炴椂浠凤細鍚?,
                            "   - 鍦板潃锛氳タ婀栧ぇ閬?1 鍙?,
                            "   - 渚涘簲鍟嗭細amap",
                            "",
                            "### 棰勮鎻愰啋",
                            "- 浠锋牸涓庢埧鎬佽浠ヤ笅鍗曢〉涓哄噯銆?,
                        ]
                    ),
                    "\n".join(
                        [
                            "## 楂樺痉鍦板浘棰勮",
                            "MAP_PREVIEW_JSON: {\"provider_mode\":\"mcp\",\"title\":\"鏉窞涓ゆ棩璺嚎鍥綷",\"city\":\"鏉窞\",\"center\":\"120.143222,30.236064\",\"markers\":[{\"name\":\"鏉窞涓滅珯\",\"location\":\"120.219375,30.291225\"},{\"name\":\"瑗挎箹\",\"location\":\"120.143222,30.236064\"}],\"personal_map_url\":\"https://example.com/personal-map\",\"official_map_url\":\"https://uri.amap.com/marker?position=120.143222,30.236064\",\"navigation_url\":\"https://uri.amap.com/navigation?from=foo&to=bar\"}",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 鍛ㄨ竟缇庨鎺ㄨ崘",
                            "- 涓績鐐癸細娌冲潑琛?,
                            "- 鎼滅储鍗婂緞锛?000 绫?,
                            "- 鍛戒腑鎬绘暟锛?",
                            "",
                            "### 鎺ㄨ崘鍒楄〃",
                            "1. **鐭ュ懗瑙?*锛堟澀甯彍锛?,
                            "   璺濈锛?00 m锝滃湴鍧€锛氭渤鍧婅 88 鍙?,
                            "2. **鏂扮櫧楣?*锛堝甯歌彍锛?,
                            "   璺濈锛?50 m锝滃湴鍧€锛氬崡瀹嬪尽琛?19 鍙?,
                        ]
                    ),
                    "\n".join(
                        [
                            "## 鏅偣涓茶仈璺嚎",
                            "- 鍩庡競锛氭澀宸?,
                            "- 鍑鸿鏂瑰紡锛氬叕浜?鍦伴搧",
                            "- 鏅偣椤哄簭锛氳タ婀?-> 娌冲潑琛?-> 鍗楀畫寰¤",
                            "- 鍘熷椤哄簭锛氳タ婀?-> 鍗楀畫寰¤ -> 娌冲潑琛?,
                            "- 鑷姩椤哄簭浼樺寲锛氬凡鍚敤锛堝浐瀹氶鐐癸細瑗挎箹锛?,
                            "",
                            "### 鍒嗘鏄庣粏",
                            "| 娈佃惤 | 璧风偣 | 缁堢偣 | 璺濈 | 鑰楁椂 |",
                            "| --- | --- | --- | --- | --- |",
                            "| 1 | 瑗挎箹 | 娌冲潑琛?| 2.3 km | 24鍒嗛挓 |",
                            "| 2 | 娌冲潑琛?| 鍗楀畫寰¤ | 800 m | 12鍒嗛挓 |",
                            "",
                            "### 绗?1 娈碉細瑗挎箹 -> 娌冲潑琛?,
                            "- 鍑鸿鏂瑰紡锛氬叕浜?鍦伴搧",
                            "- 璺濈锛?.3 km",
                            "- 鑰楁椂锛?4鍒嗛挓",
                            "- 绁ㄤ环鍙傝€冿細3 鍏?,
                            "- 鎬绘琛岃窛绂伙細450 绫?,
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
                            "3. 姝ヨ 150 绫冲埌娌冲潑琛?,
                            "   - 绫诲瀷锛氭琛?,
                            "   - 璺濈锛?50 绫?,
                            "   - 鍒拌揪鐐癸細娌冲潑琛?,
                            "",
                            "### 绗?2 娈碉細娌冲潑琛?-> 鍗楀畫寰¤",
                            "- 鍑鸿鏂瑰紡锛氭琛?,
                            "- 璺濈锛?00 m",
                            "- 鑰楁椂锛?2鍒嗛挓",
                            "1. 姝ヨ 800 绫冲埌鍗楀畫寰¤",
                            "   - 绫诲瀷锛氭琛?,
                            "   - 璺濈锛?00 绫?,
                            "   - 鍒拌揪鐐癸細鍗楀畫寰¤",
                            "",
                            "### 鎬讳綋浼扮畻",
                            "- 鎬昏窛绂伙細3.1 km",
                            "- 鎬昏€楁椂锛?6鍒嗛挓",
                            "- 璇存槑锛氳繖鏄垎娈甸€氬嫟鎬诲拰锛屾湭鍖呭惈鏅偣鍋滅暀鏃堕棿銆?,
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
        add_trip_destination.side_effect = lambda db, destination: destination

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
            selection_source="auto_sync_create",
            commit=False,
        )

        self.assertIs(trip, created_trip["trip"])
        structured_context = trip.constraints["structured_context"]
        self.assertIn("amap", structured_context)
        self.assertIn("railway12306", structured_context)
        self.assertIn("hotel_accommodation", structured_context)
        self.assertIn("assistant_plan", structured_context)
        self.assertIn("delivery_payload", trip.constraints)
        self.assertIn("document_markdown", trip.constraints)
        self.assertIn("price_confidence_summary", trip.constraints)
        self.assertEqual("鏉窞涓ゆ棩璺嚎鍥?, trip.constraints["delivery_payload"]["map_preview"]["title"])

        amap_cards = [card["type"] for card in structured_context["amap"]["cards"]]
        self.assertIn("stay_recommendations", amap_cards)
        self.assertIn("food_recommendations", amap_cards)
        self.assertIn("spot_route", amap_cards)
        self.assertIn("map_preview", amap_cards)
        self.assertEqual("鏈€浣庝环", structured_context["amap"]["stays"][0]["items"][0]["price_source"])

        railway_arrival = structured_context["railway12306"]["arrivals"][0]
        self.assertEqual("涓婃捣", railway_arrival["origin_city"])
        self.assertEqual("鏉窞", railway_arrival["destination_city"])
        self.assertEqual("閾佽矾12306瀹樻柟", railway_arrival["official_notice"]["娓犻亾"])

        hotel_search = structured_context["hotel_accommodation"]["searches"][0]
        self.assertEqual("鏉窞", hotel_search["destination"])
        self.assertEqual("reference", hotel_search["price_status"])

        assistant_plan = structured_context["assistant_plan"]
        self.assertIn("budget", assistant_plan)
        self.assertIn("notes", assistant_plan)
        self.assertIn("assumptions", assistant_plan)

        self.assertEqual(2, len(captured_days))
        day_one_types = [item["type"] for item in captured_days[0].items]
        day_two_types = [item["type"] for item in captured_days[1].items]
        all_item_types = [item["type"] for day in captured_days for item in day.items]

        self.assertIn("arrival_recommendation", day_one_types)
        self.assertIn("stay_recommendations", day_one_types)
        self.assertIn("spot_sequence", day_one_types)
        self.assertIn("transit", day_one_types)
        self.assertIn("food_recommendations", all_item_types)
        self.assertIn("budget_summary", day_two_types)
        self.assertIn("travel_notes", day_two_types)
        self.assertIn("planning_assumptions", day_two_types)

        transit_items = [item for item in captured_days[0].items if item.get("type") == "transit"]
        self.assertTrue(any(item.get("step_details") for item in transit_items))
        self.assertTrue(any(item.get("route_kind") == "spot_leg" for item in transit_items))
        self.assertIn("閰掑簵鎺ㄨ崘", trip.constraints["document_markdown"])
        self.assertIn("鍒拌揪鏂瑰紡", trip.constraints["document_markdown"])
        self.assertIn("Day 0 鍒拌揪鏃?, trip.constraints["document_markdown"])
        self.assertEqual("arrival", trip.constraints["delivery_payload"]["daily_itinerary"][0]["day_type"])
        self.assertEqual("reference", trip.constraints["price_confidence_summary"]["hotel_price_status"])
        create_session_event.assert_called()


if __name__ == "__main__":
    unittest.main()
