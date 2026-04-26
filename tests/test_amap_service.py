import unittest
from unittest.mock import MagicMock

from services.amap_service import AmapService
from services.errors import ServiceValidationError


class AmapServiceTests(unittest.TestCase):
    def test_geocode_returns_primary_item(self):
        client = MagicMock()
        client.geocode.return_value = {
            "status": "1",
            "count": "1",
            "geocodes": [
                {
                    "formatted_address": "浙江省杭州市西湖区西湖风景名胜区",
                    "province": "浙江省",
                    "city": "杭州市",
                    "district": "西湖区",
                    "adcode": "330106",
                    "location": "120.130663,30.240018",
                    "level": "兴趣点",
                }
            ],
        }
        service = AmapService(client=client)

        payload = service.geocode(address="杭州西湖", city="杭州")

        self.assertEqual(1, payload["count"])
        self.assertEqual("杭州西湖", payload["query"]["address"])
        self.assertEqual("120.130663,30.240018", payload["primary"]["location"])

    def test_search_poi_rejects_invalid_page_size(self):
        service = AmapService(client=MagicMock())
        with self.assertRaises(ServiceValidationError):
            service.search_poi(keywords="火锅", page_size=30)

    def test_route_transit_requires_city(self):
        service = AmapService(client=MagicMock())
        with self.assertRaises(ServiceValidationError):
            service.route_transit(
                origin="120.130663,30.240018",
                destination="120.153576,30.287459",
                city="",
            )

    def test_route_transit_normalizes_segment_steps(self):
        client = MagicMock()
        client.route_transit.return_value = {
            "route": {
                "transits": [
                    {
                        "distance": "2300",
                        "duration": "1560",
                        "walking_distance": "750",
                        "cost": "3",
                        "segments": [
                            {
                                "walking": {
                                    "distance": "300",
                                    "duration": "240",
                                    "steps": [
                                        {
                                            "instruction": "向东步行 300 米",
                                            "assistant_action": "龙翔桥站",
                                        }
                                    ],
                                },
                                "bus": {
                                    "buslines": [
                                        {
                                            "name": "地铁 1 号线(湘湖-萧山国际机场)",
                                            "type": "地铁线路",
                                            "departure_stop": {"name": "龙翔桥站"},
                                            "arrival_stop": {"name": "定安路站"},
                                            "via_num": "2",
                                            "distance": "1800",
                                            "duration": "480",
                                        }
                                    ]
                                },
                            },
                            {
                                "walking": {
                                    "distance": "450",
                                    "duration": "420",
                                    "steps": [
                                        {
                                            "instruction": "出站后步行 450 米到河坊街",
                                            "assistant_action": "河坊街",
                                        }
                                    ],
                                }
                            },
                        ],
                    }
                ]
            }
        }
        service = AmapService(client=client)

        payload = service.route_transit(
            origin="120.130663,30.240018",
            destination="120.170000,30.250000",
            city="杭州",
        )

        primary = payload["primary_transit"]
        self.assertEqual("3 元", primary["cost_text"])
        self.assertEqual(0, primary["transfer_count"])
        self.assertEqual(3, len(primary["steps"]))
        self.assertEqual("walk", primary["steps"][0]["type"])
        self.assertEqual("metro", primary["steps"][1]["type"])
        self.assertEqual("地铁 1 号线", primary["steps"][1]["line"])
        self.assertEqual("龙翔桥站", primary["steps"][1]["departure_stop"])
        self.assertEqual("定安路站", primary["steps"][1]["arrival_stop"])
        self.assertEqual("河坊街", primary["steps"][2]["destination_name"])

    def test_weather_rejects_invalid_extensions(self):
        service = AmapService(client=MagicMock())
        with self.assertRaises(ServiceValidationError):
            service.weather(city="杭州", extensions="weekly")

    def test_extract_structured_context_parses_route_and_stay_cards(self):
        structured = AmapService.extract_structured_context(
            [
                "\n".join(
                    [
                        "## 路线规划",
                        "- 起点：杭州东站",
                        "- 终点：西湖",
                        "- 出行方式：驾车",
                        "距离：8.2 km",
                        "预计耗时：24分钟",
                        "打车参考价：32 元",
                        "",
                        "### 逐步换乘",
                        "1. 步行 300 米到网约车上车点",
                        "   - 类型：步行",
                        "   - 距离：300 米",
                    ]
                ),
                "\n".join(
                    [
                        "## 住宿推荐（酒店/民宿）",
                        "- 中心点：西湖",
                        "- 搜索半径：5000 米",
                        "- 筛选后数量：2/6",
                        "- 筛选条件：预算≤500 元，评分≥4.5，距离≤3000 米",
                        "",
                        "### 推荐列表",
                        "1. **湖畔酒店**（酒店）",
                        "   距离：900 m｜评分：4.8｜人均：380 元",
                        "   地址：西湖大道 1 号｜电话：0571-12345678",
                        "   价格来源：人均价",
                    ]
                ),
            ]
        )

        self.assertEqual("amap", structured["provider"])
        self.assertEqual(2, len(structured["cards"]))
        self.assertEqual("route", structured["cards"][0]["type"])
        self.assertEqual("杭州东站", structured["routes"][0]["origin"])
        self.assertEqual("西湖", structured["routes"][0]["destination"])
        self.assertEqual("32 元", structured["routes"][0]["taxi_cost_text"])
        self.assertEqual("步行", structured["routes"][0]["steps"][0]["type"])
        self.assertEqual(2, structured["stays"][0]["filtered_count"])
        self.assertEqual("湖畔酒店", structured["stays"][0]["items"][0]["name"])
        self.assertEqual("380 元", structured["stays"][0]["items"][0]["budget_text"])
        self.assertEqual("人均价", structured["stays"][0]["items"][0]["price_source"])

    def test_extract_structured_context_parses_spot_route_legs(self):
        structured = AmapService.extract_structured_context(
            [
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
                )
            ]
        )

        self.assertEqual(1, len(structured["routes"]))
        route = structured["routes"][0]
        self.assertEqual("spot_sequence", route["route_kind"])
        self.assertEqual(["西湖", "河坊街", "南宋御街"], route["spot_sequence"])
        self.assertEqual(["西湖", "南宋御街", "河坊街"], route["original_spot_sequence"])
        self.assertEqual("已启用（固定首点：西湖）", route["optimization_note"])
        self.assertEqual(2, len(route["legs"]))
        self.assertEqual("河坊街", route["legs"][0]["destination"])
        self.assertEqual("3 元", route["legs"][0]["ticket_cost_text"])
        self.assertEqual("地铁", route["legs"][0]["steps"][1]["type"])
        self.assertEqual("3.1 km", route["total_distance_text"])


if __name__ == "__main__":
    unittest.main()
