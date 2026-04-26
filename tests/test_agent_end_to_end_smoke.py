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
from services.trip_service import TripService


def build_session() -> ChatSession:
    return ChatSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="杭州两天旅行工作区",
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
            title="杭州两天轻松游",
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
            summary="包含到达方式、酒店、景点串联交通、美食与预算提醒。",
            plan_markdown="## 杭州两天轻松游\n围绕西湖、河坊街与南宋御街安排两天行程。",
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
                    "- 人均约 1500-1900 元，含往返高铁、酒店与市内通勤",
                    "- 酒店建议控制在 500-700 元/晚",
                    "### 注意事项",
                    "- 西湖与河坊街节假日人流较大，建议上午优先安排户外景点",
                    "- 夜间返酒店尽量避开地铁末班车前高峰",
                    "### 本次假设",
                    "- 默认从上海出发，游玩 2 天 1 晚",
                    "- 默认更偏轻松节奏，优先步行与地铁接驳",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 跨城到达建议（12306）",
                            "- 出发城市：上海",
                            "- 目的城市：杭州",
                            "- 出发日期：2026-05-01",
                            "- 推荐方式：高铁/动车（待确认车次）",
                            "- 预计耗时：1小时08分钟",
                            "- 票价参考：73 元起",
                            "- 接入状态：placeholder",
                            "- 票务状态：reference",
                            "- 数据来源：placeholder",
                            "- 方案摘要：建议优先高铁到达杭州东站，再换乘地铁前往西湖片区酒店。",
                            "",
                            "### 推荐车次",
                            "1. G7311",
                            "   - 站点：上海虹桥 -> 杭州东",
                            "   - 信息：07:00｜08:08｜1小时08分钟｜73 元起",
                            "",
                            "### 官方购票提醒",
                            "- 渠道：铁路12306官方",
                            "- 官网：https://www.12306.cn/",
                            "- App：https://kyfw.12306.cn/otn/appDownload/init",
                            "- 提醒：车次、票价、余票与购票规则请以铁路12306官网/App为准。",
                            "",
                            "### 补充说明",
                            "- 当前车次仅作查询参考，请前往铁路12306官方完成购票。",
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
                            "- 搜索半径：5000 米",
                            "- 筛选后数量：2/4",
                            "- 筛选条件：预算≤700 元，评分≥4.5，距离≤3000 米",
                            "",
                            "### 推荐列表",
                            "1. **湖畔酒店**（酒店）",
                            "   距离：900 m｜评分：4.8｜人均：580 元",
                            "   地址：西湖大道 1 号｜电话：0571-12345678",
                            "   价格来源：最低价",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 酒店民宿推荐（供应商聚合）",
                            "- 目的地：杭州",
                            "- 中心点：西湖",
                            "- 搜索半径：5000 米",
                            "- 推荐来源：amap_fallback",
                            "- 价格状态：reference",
                            "- 入住日期：2026-05-01",
                            "- 离店日期：2026-05-02",
                            "",
                            "### 推荐列表",
                            "1. **湖畔酒店**（酒店）",
                            "   - 片区：西湖",
                            "   - 距离：900 m",
                            "   - 评分：4.8",
                            "   - 价格：580 元/晚起",
                            "   - 价格来源：amap_cost",
                            "   - 是否实时价：否",
                            "   - 地址：西湖大道 1 号",
                            "   - 供应商：amap",
                            "",
                            "### 预订提醒",
                            "- 价格与房态请以下单页为准。",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 高德地图预览",
                            "MAP_PREVIEW_JSON: {\"provider_mode\":\"mcp\",\"title\":\"杭州两日路线图\",\"city\":\"杭州\",\"center\":\"120.143222,30.236064\",\"markers\":[{\"name\":\"杭州东站\",\"location\":\"120.219375,30.291225\"},{\"name\":\"西湖\",\"location\":\"120.143222,30.236064\"}],\"personal_map_url\":\"https://example.com/personal-map\",\"official_map_url\":\"https://uri.amap.com/marker?position=120.143222,30.236064\",\"navigation_url\":\"https://uri.amap.com/navigation?from=foo&to=bar\"}",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 周边美食推荐",
                            "- 中心点：河坊街",
                            "- 搜索半径：3000 米",
                            "- 命中总数：2",
                            "",
                            "### 推荐列表",
                            "1. **知味观**（杭帮菜）",
                            "   距离：300 m｜地址：河坊街 88 号",
                            "2. **新白鹿**（家常菜）",
                            "   距离：650 m｜地址：南宋御街 19 号",
                        ]
                    ),
                    "\n".join(
                        [
                            "## 景点串联路线",
                            "- 城市：杭州",
                            "- 出行方式：公交/地铁",
                            "- 景点顺序：西湖 -> 河坊街 -> 南宋御街",
                            "- 原始顺序：西湖 -> 南宋御街 -> 河坊街",
                            "- 自动顺序优化：已启用（固定首点：西湖）",
                            "",
                            "### 分段明细",
                            "| 段落 | 起点 | 终点 | 距离 | 耗时 |",
                            "| --- | --- | --- | --- | --- |",
                            "| 1 | 西湖 | 河坊街 | 2.3 km | 24分钟 |",
                            "| 2 | 河坊街 | 南宋御街 | 800 m | 12分钟 |",
                            "",
                            "### 第 1 段：西湖 -> 河坊街",
                            "- 出行方式：公交/地铁",
                            "- 距离：2.3 km",
                            "- 耗时：24分钟",
                            "- 票价参考：3 元",
                            "- 总步行距离：450 米",
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
                            "3. 步行 150 米到河坊街",
                            "   - 类型：步行",
                            "   - 距离：150 米",
                            "   - 到达点：河坊街",
                            "",
                            "### 第 2 段：河坊街 -> 南宋御街",
                            "- 出行方式：步行",
                            "- 距离：800 m",
                            "- 耗时：12分钟",
                            "1. 步行 800 米到南宋御街",
                            "   - 类型：步行",
                            "   - 距离：800 米",
                            "   - 到达点：南宋御街",
                            "",
                            "### 总体估算",
                            "- 总距离：3.1 km",
                            "- 总耗时：36分钟",
                            "- 说明：这是分段通勤总和，未包含景点停留时间。",
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
        self.assertEqual("杭州两日路线图", trip.constraints["delivery_payload"]["map_preview"]["title"])

        amap_cards = [card["type"] for card in structured_context["amap"]["cards"]]
        self.assertIn("stay_recommendations", amap_cards)
        self.assertIn("food_recommendations", amap_cards)
        self.assertIn("spot_route", amap_cards)
        self.assertIn("map_preview", amap_cards)
        self.assertEqual("最低价", structured_context["amap"]["stays"][0]["items"][0]["price_source"])

        railway_arrival = structured_context["railway12306"]["arrivals"][0]
        self.assertEqual("上海", railway_arrival["origin_city"])
        self.assertEqual("杭州", railway_arrival["destination_city"])
        self.assertEqual("铁路12306官方", railway_arrival["official_notice"]["渠道"])

        hotel_search = structured_context["hotel_accommodation"]["searches"][0]
        self.assertEqual("杭州", hotel_search["destination"])
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
        self.assertIn("酒店推荐", trip.constraints["document_markdown"])
        self.assertIn("到达方式", trip.constraints["document_markdown"])
        self.assertIn("Day 0 到达日", trip.constraints["document_markdown"])
        self.assertEqual("arrival", trip.constraints["delivery_payload"]["daily_itinerary"][0]["day_type"])
        self.assertEqual("reference", trip.constraints["price_confidence_summary"]["hotel_price_status"])
        create_session_event.assert_called()


if __name__ == "__main__":
    unittest.main()
