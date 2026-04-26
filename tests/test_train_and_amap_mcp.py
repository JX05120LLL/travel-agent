from services.amap_mcp_service import AmapMcpService
from services.train_12306_service import (
    JisuApiTrainProvider,
    PlaceholderTrain12306Provider,
    RailTripQuery,
    Train12306Service,
)


class FakeAmapService:
    def geocode(self, *, address, city=None):
        locations = {
            "杭州东站": "120.219375,30.291225",
            "西湖": "120.143222,30.236064",
        }
        return {
            "primary": {
                "formatted_address": f"{city or ''}{address}",
                "location": locations.get(address, "120.000000,30.000000"),
            }
        }


class FakeAmapMcpService(AmapMcpService):
    def __init__(self):
        super().__init__(amap_service=FakeAmapService())
        self.mcp_url = "https://example.invalid/mcp"
        self.personal_map_tools = ["maps_schema_personal_map", "create_personal_map"]
        self.personal_map_tool = self.personal_map_tools[0]

    def _call_mcp_tool(self, tool_name, arguments):
        if tool_name == "maps_schema_personal_map":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "{\"url\":\"https://example.com/personal-map?id=123\"}",
                        }
                    ]
                },
            }
        raise AssertionError("should not fall through to secondary tool")


class FailingAmapService:
    def geocode(self, *, address, city=None):
        raise Exception("rest geocode unavailable")


class FakeAmapMcpMarkerFallbackService(AmapMcpService):
    def __init__(self):
        super().__init__(amap_service=FailingAmapService())
        self.mcp_url = "https://example.invalid/mcp"
        self.personal_map_tools = ["maps_schema_personal_map"]
        self.personal_map_tool = self.personal_map_tools[0]

    def _call_mcp_tool(self, tool_name, arguments):
        if tool_name == "maps_text_search":
            keyword = arguments.get("keywords")
            if keyword == "上海虹桥站":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": '{"pois":[{"id":"B00155MPRL","name":"\u4e0a\u6d77\u8679\u6865\u7ad9","address":"\u7533\u8d35\u8def1500\u53f7"}]}'
                            }
                        ]
                    },
                }
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"pois":[{"id":"B00155FXB3","name":"\u5916\u6ee9","address":"\u4e2d\u5c71\u4e1c\u4e8c\u8def1\u53f7"}]}'
                        }
                    ]
                },
            }
        if tool_name == "maps_search_detail":
            poi_id = arguments.get("id")
            if poi_id == "B00155MPRL":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": '{"id":"B00155MPRL","name":"\u4e0a\u6d77\u8679\u6865\u7ad9","location":"121.320081,31.193964","address":"\u7533\u8d35\u8def1500\u53f7","type":"\u4ea4\u901a\u8bbe\u65bd\u670d\u52a1;\u706b\u8f66\u7ad9;\u706b\u8f66\u7ad9"}'
                            }
                        ]
                    },
                }
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"id":"B00155FXB3","name":"\u5916\u6ee9","location":"121.490317,31.241701","address":"\u4e2d\u5c71\u4e1c\u4e8c\u8def1\u53f7","type":"\u98ce\u666f\u540d\u80dc;\u98ce\u666f\u540d\u80dc\u76f8\u5173;\u65c5\u6e38\u666f\u70b9"}'
                        }
                    ]
                },
            }
        if tool_name == "maps_schema_personal_map":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": 'amapuri://workInAmap/createWithToken?polymericId=test&from=MCP'
                        }
                    ]
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")


class FakeJisuProvider(JisuApiTrainProvider):
    def __init__(self):
        self.appkey = "fake"
        self.endpoint = "https://example.invalid"
        self.timeout_seconds = 1

    def _do_search(self, payload):
        return {
            "status": 0,
            "result": {
                "list": [
                    {
                        "trainno": "G7501",
                        "startstation": "上海虹桥",
                        "endstation": "杭州东",
                        "departuretime": "08:00",
                        "arrivaltime": "08:48",
                        "costtime": "48分钟",
                        "price": "73",
                        "remain": "有票",
                    }
                ]
            },
        }


def test_jisu_provider_normalizes_train_candidates():
    payload = FakeJisuProvider().search_trips(
        RailTripQuery(origin_city="上海", destination_city="杭州", depart_date="2026-05-01")
    ).to_dict()

    assert payload["provider"] == "jisu_train_api"
    assert payload["candidates"][0]["train_no"] == "G7501"
    assert payload["candidates"][0]["depart_station"] == "上海虹桥"
    assert payload["candidates"][0]["arrive_station"] == "杭州东"
    assert payload["official_notice"]["website_url"] == "https://www.12306.cn/"


def test_train_service_falls_back_to_placeholder_without_keys():
    payload = Train12306Service(providers=[PlaceholderTrain12306Provider()]).plan_arrival(
        origin_city="上海",
        destination_city="杭州",
        depart_date="2026-05-01",
    )

    assert payload["provider_mode"] == "placeholder"
    assert payload["provider_status"]["degraded"] is True
    assert payload["official_notice"]["website_url"] == "https://www.12306.cn/"


def test_amap_map_preview_falls_back_to_uri_links_without_mcp_key(monkeypatch):
    monkeypatch.delenv("AMAP_MCP_KEY", raising=False)
    monkeypatch.delenv("AMAP_MCP_URL", raising=False)
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    service = AmapMcpService(amap_service=FakeAmapService())

    payload = service.build_map_preview(title="杭州两日游", city="杭州", points="杭州东站 -> 西湖")

    assert payload["provider_mode"] == "fallback_link"
    assert payload["markers"][0]["name"] == "杭州杭州东站"
    assert payload["navigation_url"].startswith("https://uri.amap.com/navigation")
    assert payload["official_map_url"].startswith("https://uri.amap.com/marker")


def test_amap_map_preview_extracts_personal_map_url_from_nested_text_payload():
    payload = FakeAmapMcpService().build_map_preview(
        title="杭州两日游",
        city="杭州",
        points="杭州东站 -> 西湖",
    )

    assert payload["provider_mode"] == "mcp"
    assert payload["personal_map_url"] == "https://example.com/personal-map?id=123"
    assert payload["personal_map_open_url"] == "https://example.com/personal-map?id=123"
    assert payload["degraded_reason"] is None


def test_amap_map_preview_can_resolve_markers_via_mcp_when_rest_geocode_fails():
    payload = FakeAmapMcpMarkerFallbackService().build_map_preview(
        title="\u4e0a\u6d77\u4e24\u65e5\u6e38",
        city="\u4e0a\u6d77",
        points="\u4e0a\u6d77\u8679\u6865\u7ad9 -> \u5916\u6ee9",
    )

    assert payload["provider_mode"] == "mcp"
    assert payload["markers"][0]["name"] == "\u4e0a\u6d77\u8679\u6865\u7ad9"
    assert payload["markers"][0]["location"] == "121.320081,31.193964"
    assert payload["personal_map_url"].startswith("amapuri://workInAmap/createWithToken")
    assert payload["personal_map_open_url"].startswith("https://uri.amap.com/marker?markers=")
