import sys
import types
import unittest
from unittest.mock import patch

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

from tools.train_12306 import plan_12306_arrival


def _invoke_tool(tool_obj, payload):
    if hasattr(tool_obj, "invoke"):
        return tool_obj.invoke(payload)
    return tool_obj(**payload)


class Train12306ToolTests(unittest.TestCase):
    def test_plan_12306_arrival_formats_placeholder_output(self):
        fake_payload = {
            "provider": "placeholder_train_12306",
            "provider_mode": "placeholder",
            "origin_city": "上海",
            "destination_city": "杭州",
            "depart_date": "2026-05-01",
            "recommended_mode": "高铁/动车（待确认车次）",
            "duration_text": "约 45-60 分钟",
            "price_text": "二等座约 80-120 元（以 12306 官方为准）",
            "booking_status": "official_redirect",
            "summary": "先按上海出发、杭州到达预留高铁到达链路，待补真实车次后再确认。",
            "notes": ["当前暂未获取到真实车次，请稍后重试。"],
            "candidates": [],
            "official_notice": {
                "channel_name": "铁路12306官方",
                "website_url": "https://www.12306.cn/",
                "app_url": "https://kyfw.12306.cn/otn/appDownload/init",
                "notice": "车次、票价、余票与购票规则请以铁路12306官网/App为准。",
            },
            "ticket_status": "placeholder",
            "data_source": "placeholder_train_12306",
            "fetched_at": "2026-04-25T10:00:00Z",
            "degraded_reason": "未接入实时车次数据",
            "provider_status": {
                "selected_provider": "placeholder_train_12306",
                "fallback_errors": ["mcp12306 unavailable"],
            },
        }

        with patch("tools.train_12306.get_train_12306_service") as mock_service:
            mock_service.return_value.plan_arrival.return_value = fake_payload
            result = _invoke_tool(
                plan_12306_arrival,
                {
                    "origin_city": "上海",
                    "destination_city": "杭州",
                    "depart_date": "2026-05-01",
                },
            )

        self.assertIn("## 跨城到达建议（12306）", result)
        self.assertIn("出发城市：上海", result)
        self.assertIn("目的城市：杭州", result)
        self.assertIn("推荐方式：高铁/动车（待确认车次）", result)
        self.assertIn("数据时效：", result)
        self.assertIn("### 官方购票提醒", result)
        self.assertIn("铁路12306官方", result)
        self.assertIn("### 补充说明", result)


if __name__ == "__main__":
    unittest.main()
