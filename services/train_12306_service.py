"""铁路/12306 到达规划服务。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from dotenv import load_dotenv

from services.errors import (
    ServiceConfigError,
    ServiceIntegrationError,
    ServiceValidationError,
)
from services.external_call_guard import ExternalCallPolicy, external_call_guard

load_dotenv()

OFFICIAL_12306_WEB_URL = "https://www.12306.cn/"
OFFICIAL_12306_APP_URL = "https://kyfw.12306.cn/otn/appDownload/init"


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", []):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _iter_nested(payload: Any):
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from _iter_nested(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_nested(item)


@dataclass(slots=True)
class RailTripQuery:
    origin_city: str
    destination_city: str
    depart_date: str


@dataclass(slots=True)
class OfficialPurchaseNotice:
    channel_name: str = "铁路12306官方"
    website_url: str = OFFICIAL_12306_WEB_URL
    app_url: str = OFFICIAL_12306_APP_URL
    notice: str = "车次、票价、余票与购票规则请以铁路12306官网/App为准。"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RailTripOption:
    train_no: str | None = None
    depart_station: str | None = None
    arrive_station: str | None = None
    depart_time: str | None = None
    arrive_time: str | None = None
    duration_text: str | None = None
    seat_summary: str | None = None
    price_text: str | None = None
    price_value: float | None = None
    availability_text: str | None = None
    data_source: str = "unknown"
    is_live: bool = False
    fetched_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RailTripResult:
    provider: str
    provider_mode: str
    origin_city: str
    destination_city: str
    depart_date: str
    recommended_mode: str
    duration_text: str
    price_text: str
    booking_status: str
    summary: str
    notes: list[str] = field(default_factory=list)
    candidates: list[RailTripOption] = field(default_factory=list)
    official_notice: OfficialPurchaseNotice = field(default_factory=OfficialPurchaseNotice)
    ticket_status: str = "reference"
    data_source: str = "unknown"
    fetched_at: str | None = None
    degraded_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_mode": self.provider_mode,
            "origin_city": self.origin_city,
            "destination_city": self.destination_city,
            "depart_date": self.depart_date,
            "recommended_mode": self.recommended_mode,
            "duration_text": self.duration_text,
            "price_text": self.price_text,
            "booking_status": self.booking_status,
            "summary": self.summary,
            "notes": list(self.notes),
            "candidates": [item.to_dict() for item in self.candidates],
            "official_notice": self.official_notice.to_dict(),
            "ticket_status": self.ticket_status,
            "data_source": self.data_source,
            "fetched_at": self.fetched_at,
            "degraded_reason": self.degraded_reason,
        }


class RailProvider(Protocol):
    provider_name: str

    def search_trips(self, query: RailTripQuery) -> RailTripResult:
        ...

    def build_official_notice(self, query: RailTripQuery) -> OfficialPurchaseNotice:
        ...


class Official12306LinkBuilder:
    provider_name = "official_12306_notice"

    def search_trips(self, query: RailTripQuery) -> RailTripResult:
        raise ServiceConfigError("官方提醒构建器不直接查询车次。")

    def build_official_notice(self, query: RailTripQuery) -> OfficialPurchaseNotice:
        return OfficialPurchaseNotice()


class JisuApiTrainProvider:
    """极速数据等国内第三方火车票查询 provider。

    只做查询参考，不做购票闭环；最终车次、票价、余票以 12306 官方为准。
    """

    provider_name = "jisu_train_api"

    def __init__(self) -> None:
        self.endpoint = (
            os.getenv("JISU_TRAIN_BASE_URL", "").strip()
            or "https://api.jisuapi.com/train/ticket"
        )
        self.appkey = os.getenv("JISU_TRAIN_APPKEY", "").strip()
        self.timeout_seconds = float(os.getenv("JISU_TRAIN_TIMEOUT_SECONDS", "10") or "10")

    def build_official_notice(self, query: RailTripQuery) -> OfficialPurchaseNotice:
        return OfficialPurchaseNotice()

    def search_trips(self, query: RailTripQuery) -> RailTripResult:
        if not self.appkey:
            raise ServiceConfigError("未配置 JISU_TRAIN_APPKEY，已自动降级到其他火车票来源。")

        payload = {
            "appkey": self.appkey,
            "start": query.origin_city,
            "end": query.destination_city,
            "date": query.depart_date,
        }
        policy = ExternalCallPolicy(
            provider="railway12306",
            operation="jisu_train_api",
            ttl_seconds=10 * 60,
            rate_limit=30,
            rate_window_seconds=60,
            circuit_breaker_threshold=3,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        raw = external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_search(payload),
        )
        candidates = self._extract_candidates(raw)
        if not candidates:
            raise ServiceIntegrationError("第三方火车票接口未返回可用车次。")

        best = candidates[0]
        return RailTripResult(
            provider=self.provider_name,
            provider_mode="third_party",
            origin_city=query.origin_city,
            destination_city=query.destination_city,
            depart_date=query.depart_date,
            recommended_mode="高铁/动车/火车",
            duration_text=best.duration_text or "待补充",
            price_text=best.price_text or "待补充",
            booking_status="reference_only",
            summary=(
                f"第三方查询到 {best.train_no or '候选车次'}，"
                f"可从 {best.depart_station or query.origin_city} 前往 "
                f"{best.arrive_station or query.destination_city}。"
            ),
            notes=[
                "当前车次来自第三方查询接口，仅作行程规划参考。",
                "票价、余票、购票规则与最终行程请以铁路12306官网/App为准。",
            ],
            candidates=candidates[:8],
            ticket_status="reference",
            data_source=self.provider_name,
            fetched_at=_utc_now_iso(),
        )

    def _do_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "User-Agent": "travel-agent/1.0",
            "Accept": "application/json,text/plain,*/*",
        }
        attempts = [
            dict(payload),
            {
                "appkey": payload["appkey"],
                "from": payload["start"],
                "to": payload["end"],
                "date": payload["date"],
            },
            {
                "appkey": payload["appkey"],
                "fromStation": payload["start"],
                "toStation": payload["end"],
                "trainDate": payload["date"],
            },
        ]
        last_error = "第三方火车票接口查询失败。"
        for params in attempts:
            try:
                response = httpx.get(
                    self.endpoint,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return self._parse_json_response(response)
            except ServiceIntegrationError as exc:
                last_error = str(exc)
                continue
            except httpx.TimeoutException as exc:
                last_error = f"第三方火车票查询超时：{exc}"
                continue
            except httpx.HTTPStatusError as exc:
                last_error = f"第三方火车票接口返回错误：{exc.response.status_code}"
                continue
            except httpx.HTTPError as exc:
                last_error = f"第三方火车票查询失败：{exc}"
                continue
        raise ServiceIntegrationError(last_error)

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        text = response.text or ""
        content_type = (response.headers.get("content-type") or "").lower()
        if response.status_code == 202 or "<html" in text.lower() or "text/html" in content_type:
            raise ServiceIntegrationError("第三方火车票接口返回 HTML/网关页，已自动降级。")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceIntegrationError("第三方火车票接口返回非 JSON 数据。") from exc

        status = _first_non_empty(payload.get("status"), payload.get("code"), payload.get("error_code"))
        message = _first_non_empty(payload.get("msg"), payload.get("message"), payload.get("reason"))
        if str(status) not in {"", "0", "1", "200", "success", "None"}:
            raise ServiceIntegrationError(f"第三方火车票接口业务错误：{message or status}")
        return payload

    @staticmethod
    def _extract_candidates(payload: dict[str, Any]) -> list[RailTripOption]:
        candidates: list[RailTripOption] = []
        fetched_at = _utc_now_iso()
        for node in _iter_nested(payload):
            if not isinstance(node, dict):
                continue
            train_no = _first_non_empty(
                node.get("trainno"),
                node.get("train_no"),
                node.get("trainNum"),
                node.get("station_train_code"),
                node.get("checi"),
            )
            if not train_no:
                continue
            depart_station = _first_non_empty(
                node.get("startstation"),
                node.get("from_station_name"),
                node.get("depart_station"),
                node.get("departureStationName"),
            )
            arrive_station = _first_non_empty(
                node.get("endstation"),
                node.get("to_station_name"),
                node.get("arrive_station"),
                node.get("arrivalStationName"),
            )
            depart_time = _first_non_empty(
                node.get("departuretime"),
                node.get("start_time"),
                node.get("depart_time"),
                node.get("departureTime"),
            )
            arrive_time = _first_non_empty(
                node.get("arrivaltime"),
                node.get("arrive_time"),
                node.get("arrivalTime"),
            )
            duration_text = _first_non_empty(
                node.get("costtime"),
                node.get("duration"),
                node.get("duration_text"),
                node.get("lishi"),
                node.get("run_time"),
            )
            seat_summary = _first_non_empty(
                node.get("seat_summary"),
                node.get("seat"),
                node.get("seats"),
                node.get("seatName"),
            )
            price_text = _first_non_empty(
                node.get("price_text"),
                node.get("price"),
                node.get("minprice"),
                node.get("min_price"),
                node.get("ticketPrice"),
            )
            availability_text = _first_non_empty(
                node.get("availability_text"),
                node.get("remain"),
                node.get("surplus"),
                node.get("ticketNum"),
                node.get("num"),
            )
            if isinstance(seat_summary, (list, dict)):
                seat_summary = json.dumps(seat_summary, ensure_ascii=False)
            if isinstance(availability_text, (list, dict)):
                availability_text = json.dumps(availability_text, ensure_ascii=False)
            candidates.append(
                RailTripOption(
                    train_no=str(train_no),
                    depart_station=str(depart_station) if depart_station else None,
                    arrive_station=str(arrive_station) if arrive_station else None,
                    depart_time=str(depart_time) if depart_time else None,
                    arrive_time=str(arrive_time) if arrive_time else None,
                    duration_text=str(duration_text) if duration_text else None,
                    seat_summary=str(seat_summary) if seat_summary else None,
                    price_text=str(price_text) if price_text else None,
                    price_value=_safe_float(price_text),
                    availability_text=str(availability_text) if availability_text else None,
                    data_source="jisu_train_api",
                    is_live=False,
                    fetched_at=fetched_at,
                    raw=dict(node),
                )
            )

        deduped: dict[tuple[str | None, str | None, str | None], RailTripOption] = {}
        for item in candidates:
            key = (item.train_no, item.depart_time, item.arrive_time)
            deduped.setdefault(key, item)
        return list(deduped.values())


class MCP12306Provider:
    """社区 12306 MCP provider。"""

    provider_name = "mcp12306"

    def __init__(self) -> None:
        self.endpoint = os.getenv("MCP_12306_HTTP_URL", "").strip()
        self.timeout_seconds = float(os.getenv("MCP_12306_TIMEOUT_SECONDS", "15") or "15")

    def build_official_notice(self, query: RailTripQuery) -> OfficialPurchaseNotice:
        return OfficialPurchaseNotice()

    def search_trips(self, query: RailTripQuery) -> RailTripResult:
        if not self.endpoint:
            raise ServiceConfigError("MCP 12306 查询未配置，已自动回退到其他来源。")

        payload = {
            "from_station": query.origin_city,
            "to_station": query.destination_city,
            "train_date": query.depart_date,
        }
        try:
            raw = self._execute_ticket_query(payload)
        except ServiceIntegrationError as exc:
            if not self._should_retry_with_station_search(exc):
                raise
            resolved_payload = dict(payload)
            resolved_payload["from_station"] = self._resolve_station_name(query.origin_city)
            resolved_payload["to_station"] = self._resolve_station_name(query.destination_city)
            raw = self._execute_ticket_query(resolved_payload)
        candidates = [self._normalize_candidate(item) for item in raw.get("trains") or []]
        if not candidates:
            raise ServiceIntegrationError("MCP 12306 未返回可用车次。")
        self._enrich_candidate_prices(query=query, candidates=candidates)
        best = candidates[0]
        return RailTripResult(
            provider=self.provider_name,
            provider_mode="mcp",
            origin_city=query.origin_city,
            destination_city=query.destination_city,
            depart_date=query.depart_date,
            recommended_mode="高铁/动车",
            duration_text=best.duration_text or "待补充",
            price_text=best.price_text or "待补充",
            booking_status="reference_only",
            summary=(
                f"建议优先选择 {best.train_no or '高铁/动车'}，"
                f"从 {best.depart_station or query.origin_city} 到 {best.arrive_station or query.destination_city}。"
            ),
            notes=["当前车次仅作查询参考，请前往铁路12306官方完成购票。"],
            candidates=candidates[:5],
            ticket_status="reference",
            data_source="mcp12306",
            fetched_at=_utc_now_iso(),
        )

    def _execute_ticket_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        policy = ExternalCallPolicy(
            provider="railway12306",
            operation="mcp_query_tickets",
            ttl_seconds=10 * 60,
            rate_limit=40,
            rate_window_seconds=60,
            circuit_breaker_threshold=5,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_search(payload),
        )

    @staticmethod
    def _should_retry_with_station_search(error: ServiceIntegrationError) -> bool:
        message = str(error)
        return "车站名称无效" in message or "未找到匹配的车站" in message

    def _do_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = None
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                session_id = self._initialize_session(client)
                self._notify_initialized(client, session_id)
                raw = self._call_tool(
                    client,
                    session_id=session_id,
                    tool_name="query-tickets",
                    arguments=payload,
                )
                return self._extract_query_tickets_payload(raw)
        except httpx.TimeoutException as exc:
            raise ServiceIntegrationError("MCP 12306 查询超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise ServiceIntegrationError(f"MCP 12306 查询失败：{exc.response.status_code}") from exc
        except (ValueError, httpx.HTTPError) as exc:
            raise ServiceIntegrationError(f"MCP 12306 查询异常：{exc}") from exc
        finally:
            if session_id:
                try:
                    with httpx.Client(timeout=5) as client:
                        client.delete(self.endpoint, headers={"Mcp-Session-Id": session_id})
                except Exception:
                    pass

    def _initialize_session(self, client: httpx.Client) -> str:
        response = client.post(
            self.endpoint,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "travel-agent",
                        "version": "1.0.0",
                    },
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise ServiceIntegrationError(f"MCP 12306 initialize 失败：{payload.get('error')}")
        session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        if not session_id:
            raise ServiceIntegrationError("MCP 12306 未返回 Mcp-Session-Id。")
        return session_id

    def _notify_initialized(self, client: httpx.Client, session_id: str) -> None:
        client.post(
            self.endpoint,
            headers={"Mcp-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )

    def _call_tool(
        self,
        client: httpx.Client,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        response = client.post(
            self.endpoint,
            headers={"Mcp-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise ServiceIntegrationError(f"MCP 12306 工具调用失败：{payload.get('error')}")
        result = payload.get("result") or {}
        if result.get("isError"):
            content_text = self._extract_text_content(result.get("content") or [])
            raise ServiceIntegrationError(
                f"MCP 12306 工具 {tool_name} 执行失败：{content_text or '未知错误'}"
            )
        return result

    @staticmethod
    def _extract_text_content(content: list[dict[str, Any]]) -> str:
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                return str(item.get("text"))
        return ""

    def _extract_query_tickets_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        text = self._extract_text_content(result.get("content") or [])
        if not text:
            raise ServiceIntegrationError("MCP 12306 query-tickets 未返回文本内容。")
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise ServiceIntegrationError("MCP 12306 query-tickets 返回非 JSON 文本。") from exc
        if not payload.get("success"):
            message = (
                payload.get("error")
                or payload.get("message")
                or payload.get("detail")
                or "未获取到可用车次"
            )
            raise ServiceIntegrationError(f"MCP 12306 query-tickets 失败：{message}")
        return payload

    def _fetch_price_payload(
        self,
        *,
        query: RailTripQuery,
        candidate: RailTripOption,
    ) -> dict[str, Any] | None:
        tool_arguments = {
            "from_station": query.origin_city,
            "to_station": query.destination_city,
            "train_date": query.depart_date,
            "train_code": candidate.train_no,
            "purpose_codes": "ADULT",
        }
        policy = ExternalCallPolicy(
            provider="railway12306",
            operation="mcp_query_ticket_price",
            ttl_seconds=10 * 60,
            rate_limit=40,
            rate_window_seconds=60,
            circuit_breaker_threshold=5,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps(tool_arguments, ensure_ascii=False, sort_keys=True)

        def _load() -> dict[str, Any]:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                session_id = self._initialize_session(client)
                try:
                    self._notify_initialized(client, session_id)
                    result = self._call_tool(
                        client,
                        session_id=session_id,
                        tool_name="query-ticket-price",
                        arguments=tool_arguments,
                    )
                    text = self._extract_text_content(result.get("content") or [])
                    if not text:
                        raise ServiceIntegrationError("MCP 12306 query-ticket-price 未返回文本内容。")
                    return json.loads(text)
                finally:
                    try:
                        client.delete(self.endpoint, headers={"Mcp-Session-Id": session_id})
                    except Exception:
                        pass

        try:
            payload = external_call_guard.execute(
                policy=policy,
                cache_key=cache_key,
                func=_load,
            )
        except (ServiceIntegrationError, httpx.HTTPError, ValueError):
            return None
        if not payload.get("success"):
            return None
        return payload

    def _resolve_station_name(self, raw_name: str) -> str:
        query = (raw_name or "").strip()
        if not query:
            return query
        policy = ExternalCallPolicy(
            provider="railway12306",
            operation="mcp_search_stations",
            ttl_seconds=24 * 60 * 60,
            rate_limit=40,
            rate_window_seconds=60,
            circuit_breaker_threshold=5,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps({"query": query, "limit": 5}, ensure_ascii=False, sort_keys=True)

        def _load() -> str:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                session_id = self._initialize_session(client)
                try:
                    self._notify_initialized(client, session_id)
                    result = self._call_tool(
                        client,
                        session_id=session_id,
                        tool_name="search-stations",
                        arguments={"query": query, "limit": 5},
                    )
                    text = self._extract_text_content(result.get("content") or [])
                    if not text:
                        raise ServiceIntegrationError("MCP 12306 search-stations 未返回文本内容。")
                    payload = json.loads(text)
                    if not payload.get("success"):
                        raise ServiceIntegrationError(
                            f"MCP 12306 search-stations 失败：{payload.get('message') or payload.get('error') or query}"
                        )
                    stations = payload.get("stations") or []
                    if not isinstance(stations, list) or not stations:
                        raise ServiceIntegrationError(f"MCP 12306 未找到匹配车站：{query}")
                    exact = next(
                        (
                            item
                            for item in stations
                            if isinstance(item, dict) and str(item.get("name") or "").strip() == query
                        ),
                        None,
                    )
                    best = exact or next((item for item in stations if isinstance(item, dict)), None)
                    if not isinstance(best, dict) or not str(best.get("name") or "").strip():
                        raise ServiceIntegrationError(f"MCP 12306 未找到匹配车站：{query}")
                    return str(best.get("name")).strip()
                finally:
                    try:
                        client.delete(self.endpoint, headers={"Mcp-Session-Id": session_id})
                    except Exception:
                        pass

        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=_load,
        )

    def _enrich_candidate_prices(
        self,
        *,
        query: RailTripQuery,
        candidates: list[RailTripOption],
    ) -> None:
        for candidate in candidates[:3]:
            if not candidate.train_no or candidate.price_text:
                continue
            payload = self._fetch_price_payload(query=query, candidate=candidate)
            if not isinstance(payload, dict):
                continue
            data_items = payload.get("data") or []
            if not isinstance(data_items, list):
                continue
            matched = next(
                (
                    item
                    for item in data_items
                    if isinstance(item, dict)
                    and str(item.get("train_code") or item.get("train_no") or "").strip()
                    == str(candidate.train_no).strip()
                ),
                None,
            )
            if not isinstance(matched, dict):
                matched = next((item for item in data_items if isinstance(item, dict)), None)
            if not isinstance(matched, dict):
                continue
            candidate.price_text = self._format_price_text(matched.get("prices"))
            candidate.price_value = _safe_float(candidate.price_text)
            candidate.raw["price_payload"] = matched

    @staticmethod
    def _format_price_text(prices: Any) -> str | None:
        if not isinstance(prices, dict):
            return None
        ordered = []
        for seat_name, amount in prices.items():
            if amount in (None, "", "--"):
                continue
            amount_text = str(amount)
            if not amount_text.endswith("元"):
                amount_text = f"{amount_text}元"
            ordered.append(f"{seat_name}{amount_text}")
        if not ordered:
            return None
        return " / ".join(ordered[:4])

    @staticmethod
    def _normalize_candidate(item: dict[str, Any]) -> RailTripOption:
        seats = item.get("seats") or {}
        seat_summary = None
        availability_text = None
        if isinstance(seats, dict):
            seat_bits = [
                f"{seat_name}:{seat_value}"
                for seat_name, seat_value in seats.items()
                if seat_value not in (None, "", "--")
            ]
            if seat_bits:
                seat_summary = " / ".join(seat_bits[:6])
                availability_text = seat_summary
        return RailTripOption(
            train_no=item.get("train_no") or item.get("train_code"),
            depart_station=item.get("from_station") or item.get("depart_station"),
            arrive_station=item.get("to_station") or item.get("arrive_station"),
            depart_time=item.get("start_time") or item.get("depart_time"),
            arrive_time=item.get("arrive_time"),
            duration_text=item.get("duration_text") or item.get("duration"),
            seat_summary=seat_summary or item.get("seat_summary"),
            price_text=item.get("price_text"),
            price_value=_safe_float(item.get("price_value") or item.get("price")),
            availability_text=availability_text or item.get("availability_text"),
            data_source="mcp12306",
            is_live=True,
            fetched_at=_utc_now_iso(),
            raw=dict(item),
        )


class TuniuFreeApiProvider:
    """实验性 free-api / 途牛火车票 fallback。"""

    provider_name = "tuniu_free_api"

    def __init__(self) -> None:
        self.endpoint = os.getenv("TUNIU_TRAIN_API_URL", "").strip() or "https://huoche.tuniu.com/yii.php"
        self.timeout_seconds = float(os.getenv("TUNIU_TRAIN_TIMEOUT_SECONDS", "10") or "10")

    def build_official_notice(self, query: RailTripQuery) -> OfficialPurchaseNotice:
        return OfficialPurchaseNotice()

    def search_trips(self, query: RailTripQuery) -> RailTripResult:
        payload = {
            "r": "train/trainTicket/getTickets",
            "primary[departureDate]": query.depart_date,
            "primary[departureCityName]": query.origin_city,
            "primary[arrivalCityName]": query.destination_city,
            "start": 0,
            "limit": 10,
        }
        policy = ExternalCallPolicy(
            provider="railway12306",
            operation="tuniu_free_api",
            ttl_seconds=10 * 60,
            rate_limit=20,
            rate_window_seconds=60,
            circuit_breaker_threshold=3,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        raw = external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_search(payload),
        )
        candidates = self._extract_candidates(raw)
        if not candidates:
            raise ServiceIntegrationError("实验性火车票接口未返回可用车次。")
        best = candidates[0]
        return RailTripResult(
            provider=self.provider_name,
            provider_mode="experimental",
            origin_city=query.origin_city,
            destination_city=query.destination_city,
            depart_date=query.depart_date,
            recommended_mode="高铁/动车",
            duration_text=best.duration_text or "待补充",
            price_text=best.price_text or "待补充",
            booking_status="reference_only",
            summary=(
                f"第三方查询到 {best.train_no or '车次'} 可从 "
                f"{best.depart_station or query.origin_city} 前往 {best.arrive_station or query.destination_city}。"
            ),
            notes=[
                "当前车次来自第三方免费接口，仅供规划参考。",
                "票价、余票与最终出发时间请以铁路12306官网/App为准。",
            ],
            candidates=candidates[:5],
            ticket_status="reference",
            data_source="tuniu_free_api",
            fetched_at=_utc_now_iso(),
        )

    def _do_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "Referer": "https://www.free-api.com/doc/520",
            "Accept": "application/json,text/plain,*/*",
        }
        last_error = "第三方火车票接口查询失败。"
        for method in ("GET", "POST"):
            try:
                if method == "GET":
                    response = httpx.get(
                        self.endpoint,
                        params=payload,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                else:
                    response = httpx.post(
                        self.endpoint,
                        data=payload,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                response.raise_for_status()
                return self._parse_json_response(response)
            except ServiceIntegrationError as exc:
                last_error = str(exc)
                continue
            except httpx.TimeoutException as exc:
                last_error = f"第三方火车票查询超时：{exc}"
                continue
            except httpx.HTTPStatusError as exc:
                last_error = f"第三方火车票接口返回错误：{exc.response.status_code}"
                continue
            except httpx.HTTPError as exc:
                last_error = f"第三方火车票查询失败：{exc}"
                continue
        raise ServiceIntegrationError(last_error)

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        text = response.text or ""
        content_type = (response.headers.get("content-type") or "").lower()
        if response.status_code == 202 or "<html" in text.lower() or "text/html" in content_type:
            raise ServiceIntegrationError("第三方火车票接口命中反爬/网关页，已自动降级。")
        try:
            return response.json()
        except ValueError as exc:
            raise ServiceIntegrationError("第三方火车票接口返回非 JSON 数据。") from exc

    @staticmethod
    def _extract_candidates(payload: dict[str, Any]) -> list[RailTripOption]:
        candidates: list[RailTripOption] = []
        fetched_at = _utc_now_iso()
        for node in _iter_nested(payload):
            if not isinstance(node, dict):
                continue
            train_no = _first_non_empty(
                node.get("station_train_code"),
                node.get("trainNum"),
                node.get("train_no"),
                node.get("checi"),
            )
            if not train_no:
                continue
            depart_station = _first_non_empty(
                node.get("from_station_name"),
                node.get("departureStationName"),
                node.get("from_station"),
            )
            arrive_station = _first_non_empty(
                node.get("to_station_name"),
                node.get("arrivalStationName"),
                node.get("to_station"),
            )
            depart_time = _first_non_empty(node.get("start_time"), node.get("departureTime"))
            arrive_time = _first_non_empty(node.get("arrive_time"), node.get("arrivalTime"))
            duration_text = _first_non_empty(node.get("lishi"), node.get("duration"), node.get("run_time"))
            seat_summary = _first_non_empty(node.get("seat_summary"), node.get("seat"), node.get("seatName"))
            price_text = _first_non_empty(
                node.get("price_text"),
                node.get("ticketPrice"),
                node.get("min_price"),
                node.get("price"),
            )
            availability_text = _first_non_empty(
                node.get("availability_text"),
                node.get("remain"),
                node.get("surplus"),
                node.get("ticketNum"),
            )
            candidates.append(
                RailTripOption(
                    train_no=str(train_no),
                    depart_station=str(depart_station) if depart_station else None,
                    arrive_station=str(arrive_station) if arrive_station else None,
                    depart_time=str(depart_time) if depart_time else None,
                    arrive_time=str(arrive_time) if arrive_time else None,
                    duration_text=str(duration_text) if duration_text else None,
                    seat_summary=str(seat_summary) if seat_summary else None,
                    price_text=str(price_text) if price_text else None,
                    price_value=_safe_float(price_text),
                    availability_text=str(availability_text) if availability_text else None,
                    data_source="tuniu_free_api",
                    is_live=False,
                    fetched_at=fetched_at,
                    raw=dict(node),
                )
            )

        deduped: dict[tuple[str | None, str | None, str | None], RailTripOption] = {}
        for item in candidates:
            key = (item.train_no, item.depart_time, item.arrive_time)
            deduped.setdefault(key, item)
        return list(deduped.values())


@dataclass(slots=True)
class PlaceholderTrain12306Provider:
    """真实接入前的兜底 provider。"""

    provider_name = "placeholder"

    def search_trips(self, query: RailTripQuery) -> RailTripResult:
        date_text = query.depart_date or "待补充"
        summary = (
            f"当前先按 {query.origin_city} -> {query.destination_city} 的高铁/动车到达来规划，"
            "抵达后再衔接酒店与市内行程。"
        )
        return RailTripResult(
            provider="railway12306",
            provider_mode="placeholder",
            origin_city=query.origin_city,
            destination_city=query.destination_city,
            depart_date=date_text,
            recommended_mode="高铁/动车（待确认车次）",
            duration_text="待接入实时车次后补充",
            price_text="待接入实时票价后补充",
            booking_status="placeholder",
            summary=summary,
            notes=[
                "当前为查询占位结果，暂未接入真实车次、票价与余票。",
                "建议稍后前往铁路12306官网/App核验官方车次与票价。",
            ],
            ticket_status="placeholder",
            data_source="placeholder",
            fetched_at=_utc_now_iso(),
            degraded_reason="provider_fallback",
        )

    def build_official_notice(self, query: RailTripQuery) -> OfficialPurchaseNotice:
        return OfficialPurchaseNotice()


class Train12306Service:
    """通过 provider 链输出跨城到达结构化结果。"""

    def __init__(self, providers: list[RailProvider] | None = None):
        self.official_builder = Official12306LinkBuilder()
        self.providers = providers or [
            MCP12306Provider(),
            TuniuFreeApiProvider(),
            PlaceholderTrain12306Provider(),
        ]

    def plan_arrival(
        self,
        *,
        origin_city: str,
        destination_city: str,
        depart_date: str = "",
    ) -> dict[str, Any]:
        origin = (origin_city or "").strip()
        destination = (destination_city or "").strip()
        if not origin or not destination:
            raise ServiceValidationError("12306 到达规划需要 origin_city 和 destination_city。")

        query = RailTripQuery(
            origin_city=origin,
            destination_city=destination,
            depart_date=(depart_date or "").strip(),
        )

        errors: list[str] = []
        for provider in self.providers:
            try:
                result = provider.search_trips(query)
            except (ServiceConfigError, ServiceIntegrationError) as exc:
                errors.append(str(exc))
                continue
            payload = result.to_dict()
            payload["official_notice"] = self.official_builder.build_official_notice(query).to_dict()
            payload["provider_status"] = {
                "selected_provider": payload.get("provider"),
                "selected_mode": payload.get("provider_mode"),
                "data_source": payload.get("data_source"),
                "degraded": bool(payload.get("degraded_reason")),
                "fallback_errors": list(errors),
            }
            if errors:
                payload["notes"] = list(payload.get("notes") or []) + errors
            return payload

        fallback = PlaceholderTrain12306Provider().search_trips(query).to_dict()
        fallback["official_notice"] = self.official_builder.build_official_notice(query).to_dict()
        fallback["provider_status"] = {
            "selected_provider": fallback.get("provider"),
            "selected_mode": fallback.get("provider_mode"),
            "data_source": fallback.get("data_source"),
            "degraded": True,
            "fallback_errors": list(errors),
        }
        fallback["notes"] = list(fallback.get("notes") or []) + errors
        return fallback


_train_12306_service: Train12306Service | None = None


def get_train_12306_service() -> Train12306Service:
    global _train_12306_service
    if _train_12306_service is None:
        _train_12306_service = Train12306Service()
    return _train_12306_service
