import sys
import types
import unittest
from unittest.mock import MagicMock, patch

if "langchain_core.tools" not in sys.modules:
    langchain_core = sys.modules.get("langchain_core") or types.ModuleType("langchain_core")
    tools_module = types.ModuleType("langchain_core.tools")
    messages_module = types.ModuleType("langchain_core.messages")

    def tool(func=None, *args, **kwargs):
        if func is None:
            return lambda inner: inner
        return func

    class _Message:
        def __init__(self, content=None):
            self.content = content

    tools_module.tool = tool
    langchain_core.tools = tools_module
    messages_module.AIMessage = _Message
    messages_module.HumanMessage = _Message
    messages_module.SystemMessage = _Message
    langchain_core.messages = messages_module
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.tools"] = tools_module
    sys.modules["langchain_core.messages"] = messages_module

from tools import amap as amap_tools


def invoke_tool(tool_obj, **kwargs):
    if hasattr(tool_obj, "invoke"):
        return tool_obj.invoke(kwargs)
    return tool_obj(**kwargs)


class AmapToolsSmokeTests(unittest.TestCase):
    def setUp(self):
        amap_tools._amap_service = None

    @patch("tools.amap._get_amap_service")
    def test_amap_geocode_formats_primary_result(self, get_amap_service):
        service = get_amap_service.return_value
        service.geocode.return_value = {
            "count": 1,
            "primary": {
                "formatted_address": "浙江省杭州市西湖区西湖风景名胜区",
                "location": "120.130663,30.240018",
                "province": "浙江省",
                "city": "杭州市",
                "district": "西湖区",
            },
        }

        result = invoke_tool(amap_tools.amap_geocode, address="杭州西湖", city="杭州")

        self.assertIn("【高德地理编码】", result)
        self.assertIn("坐标：120.130663,30.240018", result)
        self.assertIn("行政区：浙江省杭州市西湖区", result)
        service.geocode.assert_called_once_with(address="杭州西湖", city="杭州")

    @patch("tools.amap._get_amap_service")
    def test_amap_route_plan_resolves_addresses_and_formats_driving_result(
        self,
        get_amap_service,
    ):
        service = get_amap_service.return_value
        service.geocode.side_effect = [
            {
                "primary": {
                    "formatted_address": "杭州东站",
                    "location": "120.210000,30.290000",
                    "city": "杭州",
                }
            },
            {
                "primary": {
                    "formatted_address": "西湖",
                    "location": "120.130663,30.240018",
                    "city": "杭州",
                }
            },
        ]
        service.route_driving.return_value = {
            "primary_path": {"distance": "8200", "duration": "1440"},
            "taxi_cost": "32",
        }

        result = invoke_tool(
            amap_tools.amap_route_plan,
            origin="杭州东站",
            destination="西湖",
            mode="driving",
        )

        self.assertIn("## 路线规划", result)
        self.assertIn("- 起点：杭州东站", result)
        self.assertIn("- 终点：西湖", result)
        self.assertIn("距离：8.2 km", result)
        self.assertIn("预计耗时：24分钟", result)
        self.assertIn("打车参考价：32 元", result)
        service.route_driving.assert_called_once_with(
            origin="120.210000,30.290000",
            destination="120.130663,30.240018",
            strategy=0,
        )

    @patch("tools.amap._get_amap_service")
    def test_amap_route_plan_formats_transit_steps(self, get_amap_service):
        service = get_amap_service.return_value
        service.geocode.side_effect = [
            {
                "primary": {
                    "formatted_address": "西湖",
                    "location": "120.130663,30.240018",
                    "city": "杭州",
                }
            },
            {
                "primary": {
                    "formatted_address": "河坊街",
                    "location": "120.170000,30.250000",
                    "city": "杭州",
                }
            },
        ]
        service.route_transit.return_value = {
            "primary_transit": {
                "distance": "2300",
                "duration": "1440",
                "walking_distance": "450",
                "cost_text": "3 元",
                "steps": [
                    {
                        "type": "walk",
                        "instruction": "步行 300 米到龙翔桥站",
                        "distance": "300",
                        "destination_name": "龙翔桥站",
                    },
                    {
                        "type": "metro",
                        "instruction": "乘坐 地铁1号线，从龙翔桥站到定安路站，经过 2 站",
                        "line": "地铁1号线",
                        "departure_stop": "龙翔桥站",
                        "arrival_stop": "定安路站",
                        "via_num": 2,
                        "duration": "480",
                    },
                    {
                        "type": "walk",
                        "instruction": "步行 150 米到河坊街",
                        "distance": "150",
                        "destination_name": "河坊街",
                    },
                ],
            }
        }

        result = invoke_tool(
            amap_tools.amap_route_plan,
            origin="西湖",
            destination="河坊街",
            mode="transit",
            city="杭州",
        )

        self.assertIn("## 路线规划", result)
        self.assertIn("城市：杭州", result)
        self.assertIn("距离：2.3 km", result)
        self.assertIn("票价参考：3 元", result)
        self.assertIn("### 逐步换乘", result)
        self.assertIn("1. 步行 300 米到龙翔桥站", result)
        self.assertIn("   - 类型：步行", result)
        self.assertIn("2. 乘坐 地铁1号线，从龙翔桥站到定安路站，经过 2 站", result)
        self.assertIn("   - 上车站：龙翔桥站", result)
        self.assertIn("   - 下车站：定安路站", result)

    @patch("tools.amap._resolve_location")
    @patch("tools.amap._get_amap_service")
    def test_amap_city_route_plan_transit_degrades_to_driving_for_cross_city(
        self,
        get_amap_service,
        resolve_location,
    ):
        service = get_amap_service.return_value
        resolve_location.side_effect = [
            ("120.155070,30.274085", "杭州市", "杭州"),
            ("121.473701,31.230416", "上海市", "上海"),
        ]
        service.route_driving.return_value = {
            "primary_path": {"distance": "176000", "duration": "10800"}
        }

        result = invoke_tool(
            amap_tools.amap_city_route_plan,
            origin_city="杭州",
            destination_city="上海",
            mode="transit",
        )

        self.assertIn("## 城市路线规划", result)
        self.assertIn("高德公交/地铁路线主要面向同城", result)
        self.assertIn("跨城驾车距离：176.0 km", result)
        self.assertIn("跨城驾车耗时：3小时0分钟", result)
        service.route_driving.assert_called_once()
        service.route_transit.assert_not_called()

    @patch("tools.amap._get_amap_service")
    def test_amap_search_stays_formats_filtered_recommendations(self, get_amap_service):
        service = get_amap_service.return_value
        service.geocode.return_value = {
            "primary": {
                "formatted_address": "西湖",
                "location": "120.130663,30.240018",
                "city": "杭州",
            }
        }
        service.search_stays_with_filters.return_value = {
            "count": 2,
            "before_filter_count": 6,
            "items": [
                {
                    "name": "湖畔酒店",
                    "type": "酒店",
                    "distance": "900",
                    "rating": 4.8,
                    "cost": 380,
                    "address": "西湖大道 1 号",
                    "tel": "0571-12345678",
                },
                {
                    "name": "西湖民宿",
                    "type": "民宿",
                    "distance": "1500",
                    "rating": None,
                    "cost": None,
                    "address": "湖滨路 8 号",
                    "tel": "",
                },
            ],
        }

        result = invoke_tool(
            amap_tools.amap_search_stays,
            center="西湖",
            city="杭州",
            radius=5000,
            limit=8,
            max_budget=400,
            min_rating=4.5,
            max_distance_m=3000,
        )

        self.assertIn("## 住宿推荐（酒店/民宿）", result)
        self.assertIn("- 筛选后数量：2/6", result)
        self.assertIn("预算≤400 元", result)
        self.assertIn("评分≥4.5", result)
        self.assertIn("1. **湖畔酒店**（酒店）", result)
        self.assertIn("距离：900 m｜评分：4.8｜人均：380 元", result)
        self.assertIn("2. **西湖民宿**（民宿）", result)
        self.assertIn("评分：未知｜人均：未知", result)
        service.search_stays_with_filters.assert_called_once_with(
            location="120.130663,30.240018",
            radius=5000,
            limit=8,
            min_rating=4.5,
            max_budget=400,
            max_distance_m=3000,
            include_unknown_budget=True,
            include_unknown_rating=True,
        )

    @patch("tools.amap._get_amap_service")
    def test_amap_plan_spot_routes_expands_transit_legs_and_optimizes_order(
        self,
        get_amap_service,
    ):
        service = get_amap_service.return_value
        service.geocode.side_effect = [
            {
                "primary": {
                    "formatted_address": "西湖",
                    "location": "120.130663,30.240018",
                    "city": "杭州",
                }
            },
            {
                "primary": {
                    "formatted_address": "河坊街",
                    "location": "120.176111,30.245556",
                    "city": "杭州",
                }
            },
            {
                "primary": {
                    "formatted_address": "南宋御街",
                    "location": "120.170000,30.250000",
                    "city": "杭州",
                }
            },
        ]

        transit_map = {
            ("120.130663,30.240018", "120.170000,30.250000"): {
                "primary_transit": {
                    "distance": "1800",
                    "duration": "900",
                    "walking_distance": "350",
                    "cost_text": "3 元",
                    "steps": [
                        {
                            "type": "walk",
                            "instruction": "步行 200 米到定安路站",
                            "distance": "200",
                            "destination_name": "定安路站",
                        },
                        {
                            "type": "metro",
                            "instruction": "乘坐 地铁1号线，从龙翔桥站到定安路站，经过 1 站",
                            "line": "地铁1号线",
                            "departure_stop": "龙翔桥站",
                            "arrival_stop": "定安路站",
                            "via_num": 1,
                            "duration": "300",
                        },
                    ],
                }
            },
            ("120.130663,30.240018", "120.176111,30.245556"): {
                "primary_transit": {
                    "distance": "2400",
                    "duration": "1800",
                    "walking_distance": "500",
                    "cost_text": "4 元",
                    "steps": [
                        {
                            "type": "bus",
                            "instruction": "乘坐 7 路公交，从西湖站到河坊街站，经过 4 站",
                            "line": "7路公交",
                            "departure_stop": "西湖站",
                            "arrival_stop": "河坊街站",
                            "via_num": 4,
                            "duration": "1200",
                        }
                    ],
                }
            },
            ("120.170000,30.250000", "120.176111,30.245556"): {
                "primary_transit": {
                    "distance": "800",
                    "duration": "600",
                    "walking_distance": "150",
                    "cost_text": "2 元",
                    "steps": [
                        {
                            "type": "walk",
                            "instruction": "步行 150 米到河坊街",
                            "distance": "150",
                            "destination_name": "河坊街",
                        }
                    ],
                }
            },
            ("120.176111,30.245556", "120.170000,30.250000"): {
                "primary_transit": {
                    "distance": "900",
                    "duration": "720",
                    "walking_distance": "180",
                    "cost_text": "2 元",
                    "steps": [
                        {
                            "type": "walk",
                            "instruction": "步行 180 米到南宋御街",
                            "distance": "180",
                            "destination_name": "南宋御街",
                        }
                    ],
                }
            },
        }
        service.route_transit.side_effect = (
            lambda origin, destination, city, cityd=None: transit_map[(origin, destination)]
        )

        result = invoke_tool(
            amap_tools.amap_plan_spot_routes,
            city="杭州",
            spots="西湖, 河坊街, 南宋御街",
            mode="transit",
        )

        self.assertIn("## 景点串联路线", result)
        self.assertIn("- 原始顺序：西湖 -> 河坊街 -> 南宋御街", result)
        self.assertIn("- 景点顺序：西湖 -> 南宋御街 -> 河坊街", result)
        self.assertIn("- 自动顺序优化：已启用（固定首点：西湖）", result)
        self.assertIn("| 1 | 西湖 | 南宋御街 | 1.8 km | 15分钟 |", result)
        self.assertIn("| 2 | 南宋御街 | 河坊街 | 800 m | 10分钟 |", result)
        self.assertIn("### 第 1 段：西湖 -> 南宋御街", result)
        self.assertIn("### 第 2 段：南宋御街 -> 河坊街", result)
        self.assertIn("乘坐 地铁1号线", result)
        self.assertIn("步行 150 米到河坊街", result)
        self.assertIn("- 总距离：2.6 km", result)
        self.assertIn("- 总耗时：25分钟", result)
        self.assertGreaterEqual(service.route_transit.call_count, 3)


if __name__ == "__main__":
    unittest.main()
