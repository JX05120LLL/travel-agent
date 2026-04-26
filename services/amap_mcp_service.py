"""高德 MCP 与地图预览服务。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from services.amap_service import AmapService
from services.errors import ServiceConfigError, ServiceIntegrationError, ServiceValidationError
from services.external_call_guard import ExternalCallPolicy, external_call_guard


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _strip(value: Any) -> str:
    return str(value or "").strip()


def _split_points(value: str) -> list[str]:
    raw = value or ""
    if "->" in raw or "→" in raw or ";" in raw or "；" in raw:
        normalized = (
            raw.replace("->", "\n")
            .replace("→", "\n")
            .replace("；", "\n")
            .replace(";", "\n")
        )
        parts = normalized.split("\n")
    else:
        parts = raw.split("，")
    seen: set[str] = set()
    points: list[str] = []
    for part in parts:
        name = part.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        points.append(name)
    return points


@dataclass(slots=True)
class MapMarker:
    name: str
    location: str
    address: str | None = None
    type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MapPreview:
    provider: str = "amap"
    provider_mode: str = "fallback_link"
    title: str = "旅行地图预览"
    city: str | None = None
    center: str | None = None
    markers: list[MapMarker] = field(default_factory=list)
    route_points: list[str] = field(default_factory=list)
    personal_map_url: str | None = None
    personal_map_open_url: str | None = None
    navigation_url: str | None = None
    taxi_url: str | None = None
    official_map_url: str | None = None
    fetched_at: str = field(default_factory=_now_iso)
    degraded_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["markers"] = [item.to_dict() for item in self.markers]
        return payload


class AmapMcpService:
    """可选接入高德 MCP；缺配置时退化为高德 URI/坐标预览。"""

    def __init__(self, amap_service: AmapService | None = None) -> None:
        self.amap_service = amap_service
        self.mcp_key = os.getenv("AMAP_MCP_KEY", "").strip()
        configured_url = os.getenv("AMAP_MCP_URL", "").strip()
        if configured_url:
            self.mcp_url = configured_url
        elif self.mcp_key:
            self.mcp_url = f"https://mcp.amap.com/mcp?key={self.mcp_key}"
        else:
            self.mcp_url = ""
        self.timeout_seconds = float(os.getenv("AMAP_MCP_TIMEOUT_SECONDS", "12") or "12")
        primary_tool = os.getenv(
            "AMAP_MCP_PERSONAL_MAP_TOOL",
            "maps_schema_personal_map",
        ).strip()
        candidate_tools = os.getenv("AMAP_MCP_PERSONAL_MAP_TOOLS", "").strip()
        default_tools = [
            primary_tool or "maps_schema_personal_map",
            "maps_schema_personal_map",
            "maps_schema_create_personal_map",
            "maps_create_personal_map",
            "create_personal_map",
        ]
        if candidate_tools:
            default_tools = [part.strip() for part in candidate_tools.split(",") if part.strip()] + default_tools
        seen_tools: set[str] = set()
        self.personal_map_tools: list[str] = []
        for tool_name in default_tools:
            normalized = _strip(tool_name)
            if not normalized or normalized in seen_tools:
                continue
            seen_tools.add(normalized)
            self.personal_map_tools.append(normalized)
        self.personal_map_tool = self.personal_map_tools[0] if self.personal_map_tools else "maps_schema_personal_map"

    def build_map_preview(self, *, title: str, city: str = "", points: str = "") -> dict[str, Any]:
        point_names = _split_points(points)
        if not point_names:
            raise ServiceValidationError("地图预览至少需要 1 个点位。")

        markers = [self._resolve_marker(point, city=city) for point in point_names]
        center = markers[0].location if markers else None
        navigation_url = self._build_navigation_url(markers)
        taxi_url = self._build_taxi_url(markers)
        official_map_url = self._build_marker_url(markers) if markers else None

        preview = MapPreview(
            title=_strip(title) or "旅行地图预览",
            city=_strip(city) or None,
            center=center,
            markers=markers,
            route_points=[marker.location for marker in markers],
            navigation_url=navigation_url,
            taxi_url=taxi_url,
            official_map_url=official_map_url,
        )

        if len(markers) < 2:
            preview.degraded_reason = "点位不足 2 个，已退化为普通高德地图链接。"
            return preview.to_dict()

        try:
            mcp_payload = self.create_personal_map(
                title=preview.title,
                markers=[marker.to_dict() for marker in markers],
                route_points=preview.route_points,
            )
        except (ServiceConfigError, ServiceIntegrationError) as exc:
            preview.degraded_reason = str(exc)
        else:
            preview.provider_mode = "mcp"
            preview.personal_map_url = mcp_payload.get("personal_map_url") or mcp_payload.get("url")
            preview.personal_map_open_url = self._build_personal_map_open_url(
                personal_map_url=preview.personal_map_url,
                official_map_url=preview.official_map_url,
            )
            preview.raw = mcp_payload

        return preview.to_dict()

    def create_personal_map(
        self,
        *,
        title: str,
        markers: list[dict[str, Any]],
        route_points: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.mcp_url:
            raise ServiceConfigError("未配置 AMAP_MCP_KEY/AMAP_MCP_URL，已退化为高德地图链接。")

        point_info_list = []
        for marker in markers:
            location = _strip(marker.get("location"))
            lon, lat = self._split_location(location)
            if lon is None or lat is None:
                continue
            point_info_list.append(
                {
                    "name": _strip(marker.get("name")) or "行程点位",
                    "lon": lon,
                    "lat": lat,
                    "poiId": _strip(marker.get("id") or marker.get("poiId") or marker.get("name")) or "travel-agent-poi",
                }
            )
        if not point_info_list:
            raise ServiceValidationError("生成高德专属地图需要有效坐标点。")

        arguments = {
            "orgName": _strip(title) or "旅行地图预览",
            "lineList": [
                {
                    "title": _strip(title) or "旅行路线",
                    "pointInfoList": point_info_list,
                }
            ],
        }
        errors: list[str] = []
        for tool_name in self.personal_map_tools:
            try:
                raw = self._call_mcp_tool(tool_name, arguments)
            except ServiceIntegrationError as exc:
                errors.append(f"{tool_name}: {exc}")
                continue

            url = self._extract_first_url(raw)
            if not url:
                detail = self._extract_first_text(raw) or "未返回可用链接"
                errors.append(f"{tool_name}: {detail}")
                continue
            return {
                "provider": "amap_mcp",
                "tool": tool_name,
                "personal_map_url": url,
                "raw": raw,
                "fetched_at": _now_iso(),
            }

        detail = "；".join(errors[:3]) if errors else "MCP 未返回可用的专属地图链接。"
        raise ServiceIntegrationError(f"高德 MCP 未生成专属地图。{detail}")

    def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        policy = ExternalCallPolicy(
            provider="amap_mcp",
            operation="tools_call",
            ttl_seconds=10 * 60,
            rate_limit=40,
            rate_window_seconds=60,
            circuit_breaker_threshold=3,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps({"tool": tool_name, "arguments": arguments}, ensure_ascii=False, sort_keys=True)
        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_mcp_tool_call(tool_name, arguments),
        )

    def _do_mcp_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(self.mcp_url, json=request, headers=headers, timeout=self.timeout_seconds)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceIntegrationError("高德 MCP 调用超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise ServiceIntegrationError(f"高德 MCP 返回错误：{exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ServiceIntegrationError(f"高德 MCP 调用失败：{exc}") from exc

        text = response.text or ""
        content_type = (response.headers.get("content-type") or "").lower()
        if "text/event-stream" in content_type:
            payload = self._parse_sse_payload(text)
        else:
            try:
                payload = json.loads(text)
            except ValueError as exc:
                raise ServiceIntegrationError("高德 MCP 返回非 JSON 数据。") from exc
        if payload.get("error"):
            raise ServiceIntegrationError(f"高德 MCP 业务错误：{payload.get('error')}")
        return self._normalize_payload(payload)

    @staticmethod
    def _parse_sse_payload(text: str) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("data:"):
                chunk = line.removeprefix("data:").strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    payload = json.loads(chunk)
                except ValueError:
                    continue
                if isinstance(payload, dict):
                    candidates.append(payload)
        if not candidates:
            raise ServiceIntegrationError("高德 MCP 返回了 event-stream，但没有可解析的 JSON 结果。")
        return candidates[-1]

    @classmethod
    def _normalize_payload(cls, payload: Any) -> Any:
        if isinstance(payload, dict):
            normalized: dict[str, Any] = {}
            for key, value in payload.items():
                if key == "text" and isinstance(value, str):
                    parsed = cls._try_parse_embedded_json(value)
                    normalized[key] = parsed if parsed is not None else value
                else:
                    normalized[key] = cls._normalize_payload(value)
            return normalized
        if isinstance(payload, list):
            return [cls._normalize_payload(item) for item in payload]
        return payload

    @staticmethod
    def _try_parse_embedded_json(value: str) -> Any | None:
        text = _strip(value)
        if not text or text[0] not in "[{":
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    @staticmethod
    def _extract_first_url(payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("personal_map_url", "map_url", "url", "uri"):
                value = payload.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://", "amapuri://")):
                    return value
            for value in payload.values():
                found = AmapMcpService._extract_first_url(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = AmapMcpService._extract_first_url(item)
                if found:
                    return found
        elif isinstance(payload, str):
            parsed = AmapMcpService._try_parse_embedded_json(payload)
            if parsed is not None:
                found = AmapMcpService._extract_first_url(parsed)
                if found:
                    return found
            match = re.search(r"(https?://[^\s\"'<>]+|amapuri://[^\s\"'<>]+)", payload)
            if match:
                return match.group(1).rstrip(",，。)")
        return None

    @staticmethod
    def _extract_first_text(payload: Any) -> str | None:
        if isinstance(payload, dict):
            for key in ("message", "detail", "text", "content"):
                value = payload.get(key)
                if isinstance(value, str) and _strip(value):
                    return _strip(value)
            for value in payload.values():
                found = AmapMcpService._extract_first_text(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = AmapMcpService._extract_first_text(item)
                if found:
                    return found
        elif isinstance(payload, str) and _strip(payload):
            return _strip(payload)
        return None

    @classmethod
    def _extract_first_json_object(cls, payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            for key in ("pois", "geocodes", "location", "id", "url", "personal_map_url"):
                if key in payload:
                    return payload
            for value in payload.values():
                found = cls._extract_first_json_object(value)
                if found is not None:
                    return found
            return payload if payload else None
        if isinstance(payload, list):
            for item in payload:
                found = cls._extract_first_json_object(item)
                if found is not None:
                    return found
            return None
        if isinstance(payload, str):
            parsed = cls._try_parse_embedded_json(payload)
            if isinstance(parsed, dict):
                return cls._extract_first_json_object(parsed)
        return None

    def _resolve_marker(self, value: str, *, city: str = "") -> MapMarker:
        raw = _strip(value)
        if not raw:
            raise ServiceValidationError("点位名称不能为空。")
        if self._is_location(raw):
            return MapMarker(name=raw, location=raw)

        rest_error: ServiceIntegrationError | None = None
        try:
            return self._resolve_marker_via_rest(raw, city=city)
        except Exception as exc:
            if isinstance(exc, ServiceIntegrationError):
                rest_error = exc
            else:
                rest_error = ServiceIntegrationError(f"REST geocode 调用失败：{raw}")

        try:
            return self._resolve_marker_via_mcp(raw, city=city)
        except ServiceIntegrationError as exc:
            if rest_error is not None:
                raise ServiceIntegrationError(f"{rest_error}; {exc}") from exc
            raise

    def _resolve_marker_via_rest(self, value: str, *, city: str = "") -> MapMarker:
        if self.amap_service is None:
            self.amap_service = AmapService()
        geo = self.amap_service.geocode(address=value, city=_strip(city) or None)
        primary = geo.get("primary") or {}
        location = _strip(primary.get("location"))
        if not location:
            raise ServiceIntegrationError(f"REST geocode 未返回坐标：{value}")
        return MapMarker(
            name=primary.get("formatted_address") or value,
            location=location,
            address=primary.get("formatted_address") or None,
            type="poi",
        )

    def _resolve_marker_via_mcp(self, value: str, *, city: str = "") -> MapMarker:
        if not self.mcp_url:
            raise ServiceIntegrationError(f"无法解析地图点位：{value}")
        detail = self._search_marker_detail_via_mcp(value, city=_strip(city) or None)
        location = _strip(detail.get("location"))
        if not location:
            raise ServiceIntegrationError(f"MCP 未返回点位坐标：{value}")
        return MapMarker(
            name=_strip(detail.get("name")) or value,
            location=location,
            address=_strip(detail.get("address")) or None,
            type=_strip(detail.get("type")) or "poi",
        )

    def _search_marker_detail_via_mcp(self, value: str, *, city: str | None) -> dict[str, Any]:
        text_payload = self._call_mcp_tool(
            "maps_text_search",
            {
                "keywords": value,
                "city": city or "",
                "citylimit": bool(city),
            },
        )
        result = self._extract_first_json_object(text_payload) or {}
        pois = result.get("pois") or []
        if not pois:
            geo_payload = self._call_mcp_tool(
                "maps_geo",
                {
                    "address": value,
                    "city": city or "",
                },
            )
            geo_result = self._extract_first_json_object(geo_payload) or {}
            geocodes = geo_result.get("geocodes") or []
            if geocodes:
                primary = geocodes[0]
                return {
                    "name": _strip(primary.get("formatted_address")) or value,
                    "location": _strip(primary.get("location")),
                    "address": _strip(primary.get("formatted_address")) or value,
                    "type": "poi",
                }
            raise ServiceIntegrationError(f"MCP 未找到点位：{value}")

        primary = pois[0]
        location = _strip(primary.get("location"))
        if location:
            return primary

        poi_id = _strip(primary.get("id"))
        if not poi_id:
            raise ServiceIntegrationError(f"MCP 点位详情缺少 id：{value}")

        detail_payload = self._call_mcp_tool(
            "maps_search_detail",
            {"id": poi_id},
        )
        detail = self._extract_first_json_object(detail_payload) or {}
        if detail.get("id") or detail.get("location"):
            return detail
        raise ServiceIntegrationError(f"MCP ??????????{value}")

    @staticmethod
    def _is_location(value: str) -> bool:
        parts = value.split(",")
        if len(parts) != 2:
            return False
        try:
            float(parts[0])
            float(parts[1])
        except ValueError:
            return False
        return True

    @staticmethod
    def _split_location(value: str) -> tuple[float | None, float | None]:
        parts = _strip(value).split(",")
        if len(parts) != 2:
            return None, None
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None, None

    @staticmethod
    def _build_marker_url(markers: list[MapMarker]) -> str | None:
        if not markers:
            return None
        if len(markers) == 1:
            marker = markers[0]
            name = quote(marker.name or "地图点位")
            return (
                "https://uri.amap.com/marker?"
                f"position={marker.location}&name={name}&src=travel-agent&coordinate=gaode&callnative=0"
            )

        marker_parts: list[str] = []
        for marker in markers[:10]:
            marker_name = (marker.name or "地图点位").replace("|", " ").replace(",", " ")
            marker_parts.append(f"{marker.location},{quote(marker_name)}")
        markers_query = "|".join(marker_parts)
        return (
            "https://uri.amap.com/marker?"
            f"markers={markers_query}&src=travel-agent&coordinate=gaode&callnative=0"
        )

    @staticmethod
    def _build_personal_map_open_url(
        *,
        personal_map_url: str | None,
        official_map_url: str | None,
    ) -> str | None:
        url = _strip(personal_map_url)
        if not url:
            return official_map_url
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("amapuri://"):
            return official_map_url or url
        return official_map_url or url

    @staticmethod
    def _build_navigation_url(markers: list[MapMarker]) -> str | None:
        if len(markers) < 2:
            return None
        start = markers[0]
        end = markers[-1]
        return (
            "https://uri.amap.com/navigation?"
            f"from={start.location},{quote(start.name)}&to={end.location},{quote(end.name)}"
            "&mode=walk&policy=1&src=travel-agent&coordinate=gaode&callnative=0"
        )

    @staticmethod
    def _build_taxi_url(markers: list[MapMarker]) -> str | None:
        if len(markers) < 2:
            return None
        start = markers[0]
        end = markers[-1]
        return (
            "https://uri.amap.com/navigation?"
            f"from={start.location},{quote(start.name)}&to={end.location},{quote(end.name)}"
            "&mode=car&src=travel-agent&coordinate=gaode&callnative=0"
        )


def extract_map_preview_payloads(tool_outputs: list[str] | None) -> list[dict[str, Any]]:
    if not tool_outputs:
        return []
    payloads: list[dict[str, Any]] = []
    prefix = "MAP_PREVIEW_JSON:"
    for raw_output in tool_outputs:
        if not isinstance(raw_output, str) or prefix not in raw_output:
            continue
        for line in raw_output.splitlines():
            if not line.strip().startswith(prefix):
                continue
            raw_json = line.split(prefix, 1)[1].strip()
            try:
                payload = json.loads(raw_json)
            except ValueError:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
    return payloads
