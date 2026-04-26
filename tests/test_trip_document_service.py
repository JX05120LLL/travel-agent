import unittest
from types import SimpleNamespace

from services.trip_document_service import TripDocumentService


class TripDocumentServiceTests(unittest.TestCase):
    def test_builds_delivery_payload_and_markdown(self):
        trip = SimpleNamespace(
            title="杭州两天轻松游",
            summary="包含高铁、酒店、景点与美食的一条龙行程。",
            primary_destination="杭州",
            total_days=2,
            status="confirmed",
            itinerary_days=[
                SimpleNamespace(
                    day_no=1,
                    title="第 1 天安排",
                    city_name="杭州",
                    summary="当日景点动线：西湖 -> 河坊街",
                    items=[
                        {
                            "type": "spot_sequence",
                            "spot_sequence": ["西湖", "河坊街"],
                            "optimization_note": "已启用固定首点优化",
                            "time_period": "morning",
                        },
                        {
                            "type": "transit",
                            "from": "西湖",
                            "to": "河坊街",
                            "mode": "公交/地铁",
                            "distance_text": "2.3 km",
                            "duration_text": "24分钟",
                            "ticket_cost_text": "3 元",
                            "route_kind": "spot_leg",
                            "step_details": [
                                {
                                    "instruction": "乘坐 地铁1号线，从龙翔桥站到定安路站",
                                    "line": "地铁1号线",
                                    "departure_stop": "龙翔桥站",
                                    "arrival_stop": "定安路站",
                                }
                            ],
                            "time_period": "afternoon",
                        },
                        {
                            "type": "food_recommendations",
                            "items": [{"name": "知味观"}],
                            "time_period": "evening",
                        },
                    ],
                )
            ],
        )
        structured_context = {
            "railway12306": {
                "arrivals": [
                    {
                        "origin_city": "上海",
                        "destination_city": "杭州",
                        "recommended_mode": "高铁/动车",
                        "duration_text": "1小时08分钟",
                        "price_text": "73 元起",
                        "summary": "优先高铁到达杭州东站。",
                        "ticket_status": "reference",
                        "data_source": "placeholder",
                        "official_notice": {"notice": "请以铁路12306官网/App为准。"},
                        "candidates": [{"train_no": "G7311", "depart_station": "上海虹桥", "arrive_station": "杭州东"}],
                    }
                ]
            },
            "amap": {
                "routes": [
                    {
                        "route_kind": "point_to_point",
                        "origin": "杭州东站",
                        "destination": "湖畔酒店",
                        "mode": "地铁/步行",
                        "distance_text": "8.4 km",
                        "duration_text": "32分钟",
                        "ticket_cost_text": "4 元",
                        "steps": [
                            {
                                "instruction": "从杭州东站乘地铁 1 号线前往龙翔桥站。",
                                "line": "地铁 1 号线",
                                "departure_stop": "杭州东站",
                                "arrival_stop": "龙翔桥站",
                            },
                            {
                                "instruction": "出站后步行约 600 米到达湖畔酒店。",
                                "distance_text": "600 米",
                                "duration_text": "9 分钟",
                            },
                        ],
                    }
                ],
                "map_preview": {
                    "provider_mode": "mcp",
                    "title": "杭州两天地图预览",
                    "city": "杭州",
                    "center": "120.143222,30.236064",
                    "markers": [
                        {"name": "杭州东站", "location": "120.219375,30.291225"},
                        {"name": "西湖", "location": "120.143222,30.236064"},
                    ],
                    "personal_map_url": "https://example.com/personal-map",
                    "personal_map_open_url": "https://example.com/personal-map",
                    "official_map_url": "https://uri.amap.com/marker?position=120.143222,30.236064",
                    "navigation_url": "https://uri.amap.com/navigation?from=foo&to=bar",
                    "fetched_at": "2026-04-25T10:00:00Z",
                }
            },
            "hotel_accommodation": {
                "searches": [
                    {
                        "summary": "湖畔酒店，580 元/晚起，amap_cost，西湖",
                        "price_status": "reference",
                        "items": [
                            {
                                "name": "湖畔酒店",
                                "片区": "西湖",
                                "价格": "580 元/晚起",
                                "价格来源": "amap_cost",
                            }
                        ],
                        "notes": ["价格与房态请以下单页为准。"],
                    }
                ]
            },
            "assistant_plan": {
                "budget": {"summary": "人均约 1500-1900 元", "items": ["酒店 580 元/晚"]},
                "notes": {"summary": "已整理出行注意事项", "items": ["五一需提前预约热门景点"]},
                "assumptions": {"summary": "本轮规划使用了默认假设", "items": ["默认两天一晚"]},
                "reasons": {"summary": "已整理本次推荐理由", "items": ["交通衔接更顺"]},
            },
        }

        payload = TripDocumentService.build_delivery_payload(trip=trip, structured_context=structured_context)
        markdown = TripDocumentService.build_document_markdown(payload)
        confidence = TripDocumentService.build_price_confidence_summary(payload)

        self.assertEqual("杭州两天轻松游", payload["overview"]["title"])
        self.assertEqual("reference", payload["stay"]["price_status"])
        self.assertEqual("reference", confidence["rail_ticket_status"])
        self.assertEqual("arrival", payload["daily_itinerary"][0]["day_type"])
        self.assertEqual("Day 0 到达日", payload["daily_itinerary"][0]["title"])
        self.assertIn("transfer_to_stay_or_first_stop", payload["daily_itinerary"][0])
        self.assertIn(
            "地铁/步行",
            payload["daily_itinerary"][0]["transfer_to_stay_or_first_stop"]["transport"],
        )
        self.assertEqual("杭州两天地图预览", payload["map_preview"]["title"])
        self.assertIn("酒店推荐", markdown)
        self.assertIn("到达方式", markdown)
        self.assertIn("地图导航", markdown)
        self.assertIn("每日行程", markdown)
        self.assertIn("Day 0 到达日", markdown)
        self.assertIn("知味观", markdown)
        self.assertIn("跨城抵达", markdown)
        self.assertIn("到站后去酒店/首景点", markdown)
        self.assertIn("专属地图", markdown)
        self.assertNotIn("| --- |", markdown)

    def test_placeholder_arrival_marks_missing_real_train(self):
        trip = SimpleNamespace(
            title="杭州周末游",
            summary="先验证到达日占位文案。",
            primary_destination="杭州",
            total_days=1,
            status="draft",
            itinerary_days=[],
        )
        structured_context = {
            "railway12306": {
                "arrivals": [
                    {
                        "origin_city": "上海",
                        "destination_city": "杭州",
                        "recommended_mode": "高铁/动车（待确认车次）",
                        "duration_text": "待接入实时车次后补充",
                        "price_text": "待接入实时票价后补充",
                        "summary": "",
                        "ticket_status": "placeholder",
                        "data_source": "placeholder",
                        "official_notice": {"notice": "车次、票价、余票与购票规则请以铁路12306官网/App为准。"},
                        "candidates": [],
                    }
                ]
            }
        }

        payload = TripDocumentService.build_delivery_payload(trip=trip, structured_context=structured_context)

        self.assertEqual("arrival", payload["daily_itinerary"][0]["day_type"])
        self.assertIn("暂未获取到真实车次", payload["daily_itinerary"][0]["summary"])
        self.assertIn(
            "暂未获取到真实车次",
            payload["daily_itinerary"][0]["periods"][0]["blocks"][0]["note"],
        )
        self.assertIn(
            "暂未获取到站后细路线",
            payload["daily_itinerary"][0]["transfer_to_stay_or_first_stop"]["note"],
        )


if __name__ == "__main__":
    unittest.main()
