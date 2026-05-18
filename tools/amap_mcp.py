"""高德 MCP 地图工具。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from services.core.errors import ServiceError
from services.providers.amap_mcp_service import AmapMcpService

_amap_mcp_service: AmapMcpService | None = None


def _get_amap_mcp_service() -> AmapMcpService:
    """延迟初始化高德 MCP 服务，避免模块导入时就触发外部配置检查。"""
    global _amap_mcp_service
    if _amap_mcp_service is None:
        _amap_mcp_service = AmapMcpService()
    return _amap_mcp_service


def _render_map_preview(payload: dict) -> str:
    """把地图预览结果整理成适合大模型消费的文本。"""
    markers = payload.get("markers") or []
    lines = [
        "## 高德地图预览",
        f"- 标题：{payload.get('title') or '旅行地图预览'}",
        f"- 城市：{payload.get('city') or '未提供'}",
        f"- 生成模式：{payload.get('provider_mode') or 'fallback_link'}",
        f"- 中心点：{payload.get('center') or '未生成'}",
        f"- 生成时间：{payload.get('fetched_at') or '未知'}",
    ]

    if payload.get("degraded_reason"):
        lines.append(f"- 降级原因：{payload.get('degraded_reason')}")

    if markers:
        lines.extend(["", "### 点位"])
        for index, marker in enumerate(markers, start=1):
            lines.append(
                f"{index}. {marker.get('name') or '未命名点位'}：{marker.get('location') or '未提供坐标'}"
            )
            if marker.get("address"):
                lines.append(f"   - 地址：{marker.get('address')}")

    links = [
        ("专属地图链接", payload.get("personal_map_url")),
        ("高德打开链接", payload.get("personal_map_open_url") or payload.get("official_map_url")),
        ("导航链接", payload.get("navigation_url")),
        ("打车链接", payload.get("taxi_url")),
    ]
    visible_links = [(label, url) for label, url in links if url]
    if visible_links:
        lines.extend(["", "### 链接"])
        for label, url in visible_links:
            lines.append(f"- {label}：{url}")

    lines.append(f"MAP_PREVIEW_JSON: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines)


@tool
def build_amap_map_preview(title: str, city: str, points: str) -> str:
    """根据标题、城市和点位列表生成高德地图预览。"""
    try:
        payload = _get_amap_mcp_service().build_map_preview(
            title=title,
            city=city,
            points=points,
        )
        return _render_map_preview(payload)
    except ServiceError as exc:
        return f"高德地图预览生成失败：{exc}"
    except Exception as exc:  # pragma: no cover - 兜底保护，避免工具异常打断主链路
        return f"高德地图预览发生未预期错误：{exc}"


@tool
def create_amap_personal_map(title: str, city: str, points: str) -> str:
    """兼容旧工具名，内部仍复用同一份地图预览能力。"""
    return build_amap_map_preview.invoke(
        {
            "title": title,
            "city": city,
            "points": points,
        }
    )
