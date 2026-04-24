"""酒店/民宿聚合工具。"""

from __future__ import annotations

import re

from langchain_core.tools import tool

from services.errors import ServiceError
from services.hotel_service import (
    FliggyHotelProvider,
    HotelSearchQuery,
    HotelSearchResult,
    get_hotel_service,
)

_COORD_PATTERN = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")


def _format_rating(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"{value:.1f}"


def _format_distance(distance_text: str | None, distance_m: int | None) -> str:
    if distance_text:
        return distance_text
    if distance_m is None:
        return "未知"
    if distance_m >= 1000:
        return f"{distance_m / 1000:.1f} km"
    return f"{distance_m} m"


def _render_hotel_result(result: HotelSearchResult, *, destination: str, checkin_date: str, checkout_date: str) -> str:
    lines = [
        "## 酒店民宿推荐（供应商聚合）",
        f"- 目的地：{destination or result.city or '待补充'}",
        f"- 中心点：{result.center}",
        f"- 搜索半径：{result.radius} 米",
        f"- 推荐来源：{result.provider}",
        f"- 价格状态：{result.price_status}",
        f"- 入住日期：{checkin_date or '未指定'}",
        f"- 离店日期：{checkout_date or '未指定'}",
        f"- 数据时效：{result.fetched_at or '待补充'}",
        "",
        "### 推荐列表",
    ]
    if not result.candidates:
        lines.append("- 当前未命中可展示的酒店候选。")
    else:
        for index, item in enumerate(result.candidates, start=1):
            lines.append(f"{index}. **{item.name}**（{item.stay_type or '住宿'}）")
            lines.append(f"   - 片区：{item.district or '待补充'}")
            lines.append(f"   - 距离：{_format_distance(item.distance_text, item.distance_m)}")
            lines.append(f"   - 评分：{_format_rating(item.rating)}")
            lines.append(f"   - 价格：{item.price_text or '暂无价格'}")
            lines.append(f"   - 价格来源：{item.price_source or 'unknown'}")
            lines.append(f"   - 是否实时价：{'是' if item.is_live_price else '否'}")
            if item.room_summary:
                lines.append(f"   - 房型摘要：{item.room_summary}")
            if item.booking_url:
                lines.append(f"   - 预订链接：{item.booking_url}")
            lines.append(f"   - 地址：{item.address or '未知'}")
            if item.tel:
                lines.append(f"   - 电话：{item.tel}")
            lines.append(f"   - 供应商：{item.provider}")
    if result.notes:
        lines.extend(["", "### 预订提醒"])
        lines.extend(f"- {note}" for note in result.notes if note)
    return "\n".join(lines)


@tool
def search_hotel_stays(
    destination: str,
    center: str,
    city: str = "",
    radius: int = 5000,
    limit: int = 6,
    max_budget: float = 0,
    min_rating: float = 0,
    max_distance_m: int = 0,
    checkin_date: str = "",
    checkout_date: str = "",
) -> str:
    """酒店/民宿聚合检索。

    当前默认使用高德住宿检索，价格仅作参考；预订请引导用户前往第三方平台完成。
    """
    safe_limit = min(max(int(limit or 6), 1), 8)
    safe_radius = min(max(int(radius or 5000), 300), 15000)
    try:
        service = get_hotel_service()
        result = service.search_candidates(
            destination=destination,
            center=center,
            city=city,
            radius=safe_radius,
            limit=safe_limit,
            max_budget=max_budget if max_budget and max_budget > 0 else None,
            min_rating=min_rating if min_rating and min_rating > 0 else None,
            max_distance_m=max_distance_m if max_distance_m and max_distance_m > 0 else None,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
        )
        return _render_hotel_result(
            result,
            destination=destination or city or "",
            checkin_date=checkin_date,
            checkout_date=checkout_date,
        )
    except ServiceError as exc:
        return f"酒店民宿检索失败：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"酒店民宿检索异常：{exc}"


@tool
def search_fliggy_hotels(
    destination: str,
    center: str,
    city: str = "",
    radius: int = 5000,
    limit: int = 6,
    checkin_date: str = "",
    checkout_date: str = "",
) -> str:
    """直接查询飞猪官方酒店 provider，便于单独 smoke 与验收。"""
    try:
        provider = FliggyHotelProvider()
        service = get_hotel_service()
        location, display_center = service._ensure_location(service.amap_service, center, city)  # type: ignore[attr-defined]
        result = provider.search_candidates(
            HotelSearchQuery(
                destination=(destination or city or center).strip() or "目的地待补充",
                center=location,
                city=(city or "").strip(),
                radius=min(max(int(radius or 5000), 300), 15000),
                limit=min(max(int(limit or 6), 1), 8),
                checkin_date=checkin_date,
                checkout_date=checkout_date,
            )
        )
        result.center = display_center
        return _render_hotel_result(
            result,
            destination=destination or city or "",
            checkin_date=checkin_date,
            checkout_date=checkout_date,
        )
    except ServiceError as exc:
        return f"飞猪酒店检索失败：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"飞猪酒店检索异常：{exc}"
