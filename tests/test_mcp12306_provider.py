import json

import pytest

from services.errors import ServiceIntegrationError
from services.external_call_guard import external_call_guard
from services.train_12306_service import (
    RailTripResult,
    MCP12306Provider,
    OfficialPurchaseNotice,
    PlaceholderTrain12306Provider,
    RailTripQuery,
    RailTripOption,
    Train12306Service,
)
from tools.train_12306 import query_train_tickets_mcp_12306


def _invoke_tool(tool_obj, payload):
    if hasattr(tool_obj, "invoke"):
        return tool_obj.invoke(payload)
    return tool_obj(**payload)


class _FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "http://localhost")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        method = (json or {}).get("method")
        if method == "initialize":
            return _FakeResponse(
                {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}},
                headers={"Mcp-Session-Id": "session-123"},
            )
        if method == "notifications/initialized":
            return _FakeResponse({}, status_code=202)
        if method == "tools/call":
            tool_name = json["params"]["name"]
            if tool_name == "query-tickets":
                payload = {
                    "success": True,
                    "from_station": "上海",
                    "to_station": "杭州",
                    "train_date": "2026-05-01",
                    "count": 1,
                    "trains": [
                        {
                            "train_no": "G1234",
                            "from_station": "上海虹桥",
                            "to_station": "杭州东",
                            "start_time": "08:00",
                            "arrive_time": "09:01",
                            "duration": "01:01",
                            "seats": {
                                "second_class": "有",
                                "first_class": "5",
                            },
                        }
                    ],
                }
                return _FakeResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "content": [{"type": "text", "text": json_module.dumps(payload, ensure_ascii=False)}],
                            "isError": False,
                        },
                    }
                )
            if tool_name == "query-ticket-price":
                payload = {
                    "success": True,
                    "data": [
                        {
                            "train_code": "G1234",
                            "prices": {
                                "二等座": "73.0",
                                "一等座": "117.0",
                            },
                        }
                    ],
                }
                return _FakeResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "content": [{"type": "text", "text": json_module.dumps(payload, ensure_ascii=False)}],
                            "isError": False,
                        },
                    }
                )
        return _FakeResponse({"jsonrpc": "2.0", "id": 1, "error": {"message": "unexpected"}}, status_code=500)

    def delete(self, url, headers=None):
        self.calls.append((url, None, headers))
        return _FakeResponse({}, status_code=200)


class _FakeClientPriceFailure(_FakeClient):
    def post(self, url, json=None, headers=None):
        if (json or {}).get("method") == "tools/call" and json["params"]["name"] == "query-ticket-price":
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": "temporary price failure"}],
                    "isError": True,
                },
            }
            return _FakeResponse(payload)
        return super().post(url, json=json, headers=headers)


json_module = json


def _reset_guard():
    external_call_guard._cache.clear()  # type: ignore[attr-defined]
    external_call_guard._timestamps.clear()  # type: ignore[attr-defined]
    external_call_guard._state.clear()  # type: ignore[attr-defined]


def test_mcp_provider_search_trips_parses_candidates_and_prices(monkeypatch):
    _reset_guard()
    monkeypatch.setenv("MCP_12306_HTTP_URL", "http://127.0.0.1:18000/mcp")
    monkeypatch.setattr("services.train_12306_service.httpx.Client", _FakeClient)
    provider = MCP12306Provider()

    result = provider.search_trips(
        RailTripQuery(origin_city="上海", destination_city="杭州", depart_date="2026-05-01")
    ).to_dict()

    assert result["provider"] == "mcp12306"
    assert result["candidates"][0]["train_no"] == "G1234"
    assert result["candidates"][0]["depart_station"] == "上海虹桥"
    assert result["candidates"][0]["arrive_station"] == "杭州东"
    assert "二等座73.0元" in (result["candidates"][0]["price_text"] or "")
    assert "second_class:有" in (result["candidates"][0]["availability_text"] or "")


def test_mcp_provider_price_failure_does_not_break_ticket_result(monkeypatch):
    _reset_guard()
    monkeypatch.setenv("MCP_12306_HTTP_URL", "http://127.0.0.1:18000/mcp")
    monkeypatch.setattr("services.train_12306_service.httpx.Client", _FakeClientPriceFailure)
    provider = MCP12306Provider()

    result = provider.search_trips(
        RailTripQuery(origin_city="上海", destination_city="杭州", depart_date="2026-05-01")
    ).to_dict()

    assert result["candidates"][0]["train_no"] == "G1234"
    assert result["candidates"][0]["price_text"] is None


def test_mcp_provider_non_json_text_raises_error(monkeypatch):
    _reset_guard()
    class _BadContentClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            if (json or {}).get("method") == "tools/call" and json["params"]["name"] == "query-tickets":
                return _FakeResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "content": [{"type": "text", "text": "not-json"}],
                            "isError": False,
                        },
                    }
                )
            return super().post(url, json=json, headers=headers)

    monkeypatch.setenv("MCP_12306_HTTP_URL", "http://127.0.0.1:18000/mcp")
    monkeypatch.setattr("services.train_12306_service.httpx.Client", _BadContentClient)
    provider = MCP12306Provider()

    with pytest.raises(ServiceIntegrationError):
        provider.search_trips(
            RailTripQuery(origin_city="上海", destination_city="杭州", depart_date="2026-05-01")
        )


def test_train_service_falls_back_to_placeholder_when_upstreams_fail():
    _reset_guard()
    class _FailingProvider:
        provider_name = "failing"

        def search_trips(self, query):
            raise ServiceIntegrationError("mock upstream error")

        def build_official_notice(self, query):
            raise NotImplementedError

    service = Train12306Service(providers=[_FailingProvider(), PlaceholderTrain12306Provider()])
    payload = service.plan_arrival(
        origin_city="上海",
        destination_city="杭州",
        depart_date="2026-05-01",
    )

    assert payload["provider_mode"] == "placeholder"
    assert payload["provider_status"]["degraded"] is True
    assert "mock upstream error" in " ".join(payload["provider_status"]["fallback_errors"])


def test_query_train_tickets_mcp_tool_renders_candidate(monkeypatch):
    class _FakeMcpProvider:
        def search_trips(self, query):
            return RailTripResult(
                provider="mcp12306",
                provider_mode="mcp",
                origin_city=query.origin_city,
                destination_city=query.destination_city,
                depart_date=query.depart_date,
                recommended_mode="高铁/动车",
                duration_text="00:45",
                price_text="二等座87.0元",
                booking_status="reference_only",
                summary="建议优先选择 C2353。",
                candidates=[
                    RailTripOption(
                        train_no="C2353",
                        depart_station="上海虹桥",
                        arrive_station="杭州东",
                        depart_time="00:06",
                        arrive_time="00:51",
                        duration_text="00:45",
                        price_text="二等座87.0元",
                        availability_text="second_class:有",
                        data_source="mcp12306",
                    )
                ],
                official_notice=OfficialPurchaseNotice(),
                ticket_status="reference",
                data_source="mcp12306",
                fetched_at="2026-04-25T09:46:41Z",
            )

    monkeypatch.setattr("tools.train_12306.MCP12306Provider", lambda: _FakeMcpProvider())
    content = _invoke_tool(
        query_train_tickets_mcp_12306,
        {
            "origin_city": "上海",
            "destination_city": "杭州",
            "depart_date": "2026-05-01",
        },
    )

    assert "C2353" in content
    assert "上海虹桥 -> 杭州东" in content
    assert "官方购票提醒" in content
