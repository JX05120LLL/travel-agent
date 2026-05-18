"""酒店与民宿查询工具。"""

from __future__ import annotations

from langchain_core.tools import tool

from services.core.errors import ServiceError
from services.providers.hotel_service import (
    FliggyHotelProvider,
    HotelSearchQuery,
    HotelSearchResult,
    get_hotel_service,
)


def _format_rating(value: float | None) -> str:
    if value is None:
        return "未提供"
    return f"{value:.1f}"


def _format_distance(distance_text: str | None, distance_m: int | None) -> str:
    if distance_text:
        return distance_text
    if distance_m is None:
        return "未提供"
    if distance_m >= 1000:
        return f"{distance_m / 1000:.1f} km"
    return f"{distance_m} m"


def _format_live_price(is_live_price: bool) -> str:
    return "是" if is_live_price else "否"


def _append_if_present(lines: list[str], label: str, value: str | None) -> None:
    if value and str(value).strip():
        lines.append(f"- {label}：{value}")


def _render_hotel_result(
    result: HotelSearchResult,
    *,
    destination: str,
    checkin_date: str,
    checkout_date: str,
) -> str:
    lines = [
        "## 酒店民宿推荐（供应商聚合）",
        f"- 目的地：{destination or result.destination or result.city or '未提供'}",
        f"- 中心点：{result.center or '未提供'}",
        f"- 搜索半径：{result.radius} 米",
        f"- 推荐来源：{result.provider}",
        f"- 价格状态：{result.price_status}",
        f"- 入住日期：{checkin_date or '未提供'}",
        f"- 离店日期：{checkout_date or '未提供'}",
        f"- 数据时效：{result.fetched_at or '未知'}",
        "",
        "### 候选住宿",
    ]

    if not result.candidates:
        lines.append("- 当前没有命中合适的酒店或民宿候选。")
    else:
        for index, item in enumerate(result.candidates, start=1):
            stay_type = item.stay_type or "住宿"
            lines.append(f"{index}. **{item.name}**（{stay_type}）")
            lines.append(f"- 片区：{item.district or '未提供'}")
            lines.append(f"- 距离：{_format_distance(item.distance_text, item.distance_m)}")
            lines.append(f"- 评分：{_format_rating(item.rating)}")
            lines.append(f"- 价格：{item.price_text or '未提供'}")
            lines.append(f"- 价格来源：{item.price_source or 'unknown'}")
            lines.append(f"- 是否实时价：{_format_live_price(item.is_live_price)}")
            _append_if_present(lines, "房型摘要", item.room_summary)
            _append_if_present(lines, "预订链接", item.booking_url)
            _append_if_present(lines, "地址", item.address)
            _append_if_present(lines, "电话", item.tel)
            _append_if_present(lines, "供应商", item.provider)

    if result.notes:
        lines.extend(["", "### 预订提醒"])
        for note in result.notes:
            if note and str(note).strip():
                lines.append(f"- {note}")

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
    """查询酒店和民宿候选，输出适合大模型整理行程的住宿建议。"""
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
        return f"酒店民宿查询失败：{exc}"
    except Exception as exc:  # pragma: no cover - 兜底保护，避免工具异常打断主链路
        return f"酒店民宿查询发生未预期错误：{exc}"


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
    """直接调用飞猪供应商做住宿检索，主要用于排查供应商链路。"""
    try:
        provider = FliggyHotelProvider()
        service = get_hotel_service()
        location, display_center = service._ensure_location(service.amap_service, center, city)  # type: ignore[attr-defined]
        result = provider.search_candidates(
            HotelSearchQuery(
                destination=(destination or city or center).strip() or "未提供目的地",
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
        return f"飞猪酒店查询失败：{exc}"
    except Exception as exc:  # pragma: no cover - 兜底保护，避免工具异常打断主链路
        return f"飞猪酒店查询发生未预期错误：{exc}"
