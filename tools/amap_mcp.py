"""高德 MCP 地图预览工具。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from services.amap_mcp_service import AmapMcpService
from services.errors import ServiceError

_amap_mcp_service: AmapMcpService | None = None


def _get_amap_mcp_service() -> AmapMcpService:
    global _amap_mcp_service
    if _amap_mcp_service is None:
        _amap_mcp_service = AmapMcpService()
    return _amap_mcp_service


def _render_map_preview(payload: dict) -> str:
    markers = payload.get("markers") or []
    lines = [
        "## 高德地图预览",
        f"- 标题：{payload.get('title') or '旅行地图预览'}",
        f"- 城市：{payload.get('city') or '未指定'}",
        f"- 接入方式：{payload.get('provider_mode') or 'fallback_link'}",
        f"- 中心点：{payload.get('center') or '待补充'}",
        f"- 数据时效：{payload.get('fetched_at') or '待补充'}",
    ]
    if payload.get("degraded_reason"):
        lines.append(f"- 降级说明：{payload.get('degraded_reason')}")
    if markers:
        lines.extend(["", "### 点位"])
        for index, marker in enumerate(markers, start=1):
            lines.append(
                f"{index}. {marker.get('name') or '点位'}：{marker.get('location') or '坐标待补充'}"
            )
            if marker.get("address"):
                lines.append(f"   - 地址：{marker.get('address')}")
    links = [
        ("专属地图", payload.get("personal_map_url")),
        ("打开高德地图", payload.get("official_map_url")),
        ("导航链接", payload.get("navigation_url")),
        ("打车/驾车链接", payload.get("taxi_url")),
    ]
    visible_links = [(label, url) for label, url in links if url]
    if visible_links:
        lines.extend(["", "### 地图链接"])
        for label, url in visible_links:
            lines.append(f"- {label}：{url}")
    lines.append(f"MAP_PREVIEW_JSON: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines)


@tool
def build_amap_map_preview(title: str, city: str, points: str) -> str:
    """生成行程地图预览结构。points 支持用逗号或 -> 分隔多个景点/酒店/车站。"""
    try:
        payload = _get_amap_mcp_service().build_map_preview(
            title=title,
            city=city,
            points=points,
        )
        return _render_map_preview(payload)
    except ServiceError as exc:
        return f"高德地图预览生成失败：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"高德地图预览异常：{exc}"


@tool
def create_amap_personal_map(title: str, city: str, points: str) -> str:
    """通过高德 MCP 尝试生成专属地图；缺 MCP 配置时返回高德地图链接兜底。"""
    return build_amap_map_preview.invoke({"title": title, "city": city, "points": points})
