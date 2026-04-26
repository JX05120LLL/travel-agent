import sys
import types
import unittest
import uuid
import json
from types import SimpleNamespace

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    httpx_module.get = object
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

from services.structured_travel_service import StructuredTravelService


class StructuredTravelServiceTests(unittest.TestCase):
    def test_build_from_message_merges_railway_budget_notes_and_assumptions(self):
        message = SimpleNamespace(
            id=uuid.uuid4(),
            content="\n".join(
                [
                    "## 推荐方案",
                    "### 推荐理由",
                    "- 交通衔接更顺",
                    "- 住宿片区更适合轻松游",
                    "### 预算汇总",
                    "- 人均约 1200-1600 元，包含酒店与市内交通",
                    "- 酒店预算：500-700 元/晚",
                    "- 餐饮预算：150-250 元/天",
                    "### 注意事项",
                    "- 五一期间热门景点建议提前预约",
                    "- 晚间返程尽量避开末班车前高峰",
                    "### 本次假设",
                    "- 默认从上海出发",
                    "- 默认两天一晚轻松游",
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
                            "- 方案摘要：建议优先高铁到达杭州东站，再衔接西湖片区酒店。",
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
                            "",
                            "### 预订提醒",
                            "- 价格与房态请以下单页为准。",
                        ]
                    )
                ]
            },
        )

        structured = StructuredTravelService.build_from_message(message)

        self.assertIn("railway12306", structured)
        self.assertIn("hotel_accommodation", structured)
        self.assertIn("assistant_plan", structured)
        self.assertEqual("arrival_recommendation", structured["railway12306"]["cards"][0]["type"])
        self.assertEqual("上海", structured["railway12306"]["arrivals"][0]["origin_city"])
        self.assertEqual(
            "高铁/动车（待确认车次）",
            structured["railway12306"]["arrivals"][0]["recommended_mode"],
        )
        self.assertEqual("铁路12306官方", structured["railway12306"]["arrivals"][0]["official_notice"]["渠道"])
        hotel_search = structured["hotel_accommodation"]["searches"][0]
        self.assertEqual("杭州", hotel_search["destination"])
        self.assertEqual("amap_fallback", hotel_search["provider"])
        self.assertEqual("amap_cost", hotel_search["items"][0]["价格来源"])
        self.assertEqual("budget_summary", structured["assistant_plan"]["cards"][0]["type"])
        self.assertEqual(
            "人均约 1200-1600 元，包含酒店与市内交通",
            structured["assistant_plan"]["budget"]["summary"],
        )
        self.assertEqual(2, len(structured["assistant_plan"]["reasons"]["items"]))
        self.assertEqual(2, len(structured["assistant_plan"]["notes"]["items"]))
        self.assertEqual(2, len(structured["assistant_plan"]["assumptions"]["items"]))
        self.assertEqual(
            str(message.id),
            structured["assistant_plan"]["source_message_id"],
        )

    def test_extracts_amap_map_preview_payload(self):
        preview_payload = {
            "provider_mode": "mcp",
            "title": "杭州行程地图",
            "city": "杭州",
            "center": "120.143222,30.236064",
            "markers": [
                {"name": "杭州东站", "location": "120.219375,30.291225"},
                {"name": "西湖", "location": "120.143222,30.236064"},
            ],
            "official_map_url": "https://uri.amap.com/marker?position=120.143222,30.236064",
        }
        structured = StructuredTravelService.extract_structured_context(
            tool_outputs=[
                "## 高德地图预览\n"
                f"MAP_PREVIEW_JSON: {json.dumps(preview_payload, ensure_ascii=False)}"
            ],
            content=None,
        )

        self.assertIn("amap", structured)
        self.assertEqual("杭州行程地图", structured["amap"]["map_preview"]["title"])
        self.assertEqual("map_preview", structured["amap"]["cards"][-1]["type"])


if __name__ == "__main__":
    unittest.main()
