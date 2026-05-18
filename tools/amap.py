"""高德地图工具。"""

from __future__ import annotations

from itertools import permutations
import re

from langchain_core.tools import tool

from services.core.errors import ServiceError
from services.providers.amap_service import AmapService

_COORD_PATTERN = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
_amap_service: AmapService | None = None


def _get_amap_service() -> AmapService:
    """懒加载高德服务实例。"""
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service


def _is_coordinate(value: str) -> bool:
    return bool(_COORD_PATTERN.match((value or "").strip()))


def _format_distance(distance_text: str | int | float | None) -> str:
    if distance_text in (None, "", []):
        return "未知"
    try:
        distance = int(float(distance_text))
    except (TypeError, ValueError):
        return str(distance_text)
    if distance >= 1000:
        return f"{distance / 1000:.1f} km"
    return f"{distance} m"


def _format_duration(duration_text: str | int | float | None) -> str:
    if duration_text in (None, "", []):
        return "未知"
    try:
        seconds = int(float(duration_text))
    except (TypeError, ValueError):
        return str(duration_text)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


def _format_budget(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"{value:.0f} 元"


def _format_rating(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"{value:.1f}"


def _format_cost_text(value: str | int | float | None) -> str | None:
    if value in (None, "", []):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    if amount.is_integer():
        return f"{int(amount)} 元"
    return f"{amount:.1f} 元"


def _resolve_stay_budget(item: dict) -> tuple[float | None, str]:
    """住宿价格优先取最低价，其次使用人均。"""
    lowest_price = item.get("lowest_price")
    cost = item.get("cost")
    try:
        if lowest_price is not None:
            return float(lowest_price), "最低价"
    except (TypeError, ValueError):
        pass
    try:
        if cost is not None:
            return float(cost), "人均价"
    except (TypeError, ValueError):
        pass
    return None, "高德未返回价格"


def _safe_int(value: str | int | float | None, default: int = 10**9) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_city_name(city_name: str) -> str:
    return (city_name or "").strip().replace("市", "")


def _parse_spot_sequence(spots: str) -> list[str]:
    raw = (spots or "").strip()
    if not raw:
        return []
    normalized = (
        raw.replace("->", "|")
        .replace("→", "|")
        .replace("；", "|")
        .replace(";", "|")
        .replace("，", "|")
        .replace(",", "|")
    )
    items: list[str] = []
    seen: set[str] = set()
    for item in normalized.split("|"):
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _format_mode_label(mode: str) -> str:
    return {
        "driving": "驾车",
        "walking": "步行",
        "transit": "公交地铁",
    }.get((mode or "").strip().lower(), mode or "未知")


def _resolve_location(
    keyword_or_location: str,
    *,
    city_hint: str = "",
) -> tuple[str, str, str | None]:
    """把地址或 POI 名称解析成经纬度。"""
    text = (keyword_or_location or "").strip()
    if not text:
        raise ValueError("地点不能为空。")
    if _is_coordinate(text):
        return text, text, city_hint.strip() or None

    service = _get_amap_service()
    payload = service.geocode(address=text, city=city_hint or None)
    primary = payload.get("primary")
    if not primary or not primary.get("location"):
        raise ValueError(f"未找到地点：{text}")

    display = (
        primary.get("formatted_address")
        or primary.get("district")
        or primary.get("city")
        or text
    )
    resolved_city = primary.get("city") or city_hint.strip() or None
    return str(primary["location"]), str(display), resolved_city


def _route_between(
    *,
    service: AmapService,
    origin: str,
    destination: str,
    city: str,
    mode: str,
) -> dict:
    """查询一段路线，并统一成工具层可用结构。"""
    normalized_mode = (mode or "driving").strip().lower()
    if normalized_mode == "driving":
        payload = service.route_driving(origin=origin, destination=destination)
        primary = payload.get("primary_path") or {}
        return {
            "mode": "driving",
            "distance": primary.get("distance"),
            "duration": primary.get("duration"),
            "cost_text": _format_cost_text(payload.get("taxi_cost")),
            "walking_distance": None,
            "steps": [],
        }

    if normalized_mode == "walking":
        payload = service.route_walking(origin=origin, destination=destination)
        primary = payload.get("primary_path") or {}
        return {
            "mode": "walking",
            "distance": primary.get("distance"),
            "duration": primary.get("duration"),
            "cost_text": None,
            "walking_distance": primary.get("distance"),
            "steps": [],
        }

    payload = service.route_transit(
        origin=origin,
        destination=destination,
        city=_normalize_city_name(city),
    )
    primary = payload.get("primary_transit") or {}
    return {
        "mode": "transit",
        "distance": primary.get("distance"),
        "duration": primary.get("duration"),
        "cost_text": primary.get("cost_text"),
        "walking_distance": primary.get("walking_distance"),
        "steps": primary.get("steps") or [],
    }


def _build_fallback_steps(
    *,
    mode: str,
    destination_name: str,
    distance: str | int | float | None,
    duration: str | int | float | None,
) -> list[dict]:
    mode_label = _format_mode_label(mode)
    if mode == "walking":
        return [
            {
                "instruction": f"从当前位置步行到 {destination_name}",
                "type": "步行",
                "distance_text": _format_distance(distance),
                "duration_text": _format_duration(duration),
                "destination_name": destination_name,
            }
        ]
    return [
        {
            "instruction": f"前往 {destination_name}",
            "type": mode_label,
            "distance_text": _format_distance(distance),
            "duration_text": _format_duration(duration),
            "destination_name": destination_name,
        }
    ]


def _append_transit_step_lines(lines: list[str], steps: list[dict]) -> None:
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step.get('instruction') or '按导航前往下一段'}")
        lines.append(f"   - 类型：{step.get('type') or '步行'}")
        if step.get("line"):
            lines.append(f"   - 线路：{step['line']}")
        if step.get("departure_stop"):
            lines.append(f"   - 上车站：{step['departure_stop']}")
        if step.get("arrival_stop"):
            lines.append(f"   - 下车站：{step['arrival_stop']}")
        if step.get("via_num") not in (None, ""):
            lines.append(f"   - 站数：{step['via_num']}")
        if step.get("distance_text"):
            lines.append(f"   - 距离：{step['distance_text']}")
        if step.get("duration_text"):
            lines.append(f"   - 预计耗时：{step['duration_text']}")
        if step.get("ticket_cost_text"):
            lines.append(f"   - 票价参考：{step['ticket_cost_text']}")
        if step.get("destination_name"):
            lines.append(f"   - 到达点：{step['destination_name']}")


def _optimize_spot_order(
    *,
    service: AmapService,
    resolved_points: list[tuple[str, str, str]],
    city: str,
    mode: str,
) -> tuple[list[tuple[str, str, str]], str]:
    """在点位不多时尝试穷举更优顺序。"""
    if len(resolved_points) <= 2:
        return resolved_points, "点位不超过 2 个，无需优化。"
    if len(resolved_points) > 6:
        return resolved_points, "点位超过 6 个，为控制时延保留原始顺序。"

    best_order = resolved_points
    best_cost = None
    origin_point = resolved_points[0]

    for candidate_tail in permutations(resolved_points[1:]):
        candidate = [origin_point, *candidate_tail]
        total_distance = 0
        try:
            for index in range(len(candidate) - 1):
                leg = _route_between(
                    service=service,
                    origin=candidate[index][2],
                    destination=candidate[index + 1][2],
                    city=city,
                    mode=mode,
                )
                total_distance += _safe_int(leg.get("distance"))
        except Exception:
            continue

        if best_cost is None or total_distance < best_cost:
            best_cost = total_distance
            best_order = candidate

    if best_order == resolved_points:
        return resolved_points, "已按原始顺序执行。"
    return best_order, "已根据路线距离自动优化景点顺序。"


@tool
def amap_geocode(address: str, city: str = "") -> str:
    """把地址名称转成经纬度。"""
    try:
        payload = _get_amap_service().geocode(address=address, city=city or None)
        primary = payload.get("primary")
        if not primary:
            return f"【高德地理编码】\n- 地址：{address}\n- 匹配数：0\n- 说明：未找到可用坐标"

        area_parts = [
            primary.get("province"),
            primary.get("city"),
            primary.get("district"),
        ]
        area = " / ".join(str(item) for item in area_parts if item)
        lines = [
            "【高德地理编码】",
            f"- 地址：{primary.get('formatted_address') or address}",
            f"- 行政区：{area or '未知'}",
            f"- 坐标：{primary.get('location') or '未知'}",
            f"- 匹配数：{payload.get('count') or 0}",
        ]
        return "\n".join(lines)
    except ServiceError as exc:
        return f"高德地理编码失败：{exc}"
    except ValueError as exc:
        return f"高德地理编码参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"高德地理编码异常：{exc}"


@tool
def amap_search_poi(keywords: str, city: str = "", page_size: int = 5) -> str:
    """搜索景点、商圈、车站、酒店等 POI。"""
    try:
        payload = _get_amap_service().search_poi(
            keywords=keywords,
            city=city or None,
            page_size=min(max(page_size, 1), 10),
        )
        items = payload.get("items") or []
        lines = [
            "【高德POI搜索】",
            f"- 关键词：{keywords}",
            f"- 城市：{city or '不限'}",
            f"- 命中总数：{payload.get('count') or 0}",
            "",
            "### 候选点位",
        ]
        if not items:
            lines.append("未找到匹配的 POI。")
            return "\n".join(lines)

        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. {item.get('name') or '未知地点'}（{item.get('type') or '未知类型'}）")
            lines.append(
                f"   地址：{item.get('address') or '未知'} | 坐标：{item.get('location') or '未知'}"
            )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"高德 POI 搜索失败：{exc}"
    except ValueError as exc:
        return f"高德 POI 搜索参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"高德 POI 搜索异常：{exc}"


@tool
def amap_route_plan(
    origin: str,
    destination: str,
    mode: str = "driving",
    city: str = "",
) -> str:
    """规划驾车、步行、公交/地铁路线。"""
    try:
        service = _get_amap_service()
        origin_loc, origin_display, resolved_city_from_origin = _resolve_location(origin, city_hint=city)
        destination_loc, destination_display, resolved_city_from_dest = _resolve_location(
            destination,
            city_hint=city or resolved_city_from_origin or "",
        )
        resolved_city = city or resolved_city_from_origin or resolved_city_from_dest or ""

        route = _route_between(
            service=service,
            origin=origin_loc,
            destination=destination_loc,
            city=resolved_city,
            mode=mode,
        )
        steps = route.get("steps") or _build_fallback_steps(
            mode=route.get("mode") or mode,
            destination_name=destination_display,
            distance=route.get("distance"),
            duration=route.get("duration"),
        )

        lines = [
            "## 路线规划",
            f"- 起点：{origin_display}",
            f"- 终点：{destination_display}",
            f"- 城市：{resolved_city or '未知'}",
            f"- 出行方式：{_format_mode_label(route.get('mode') or mode)}",
            f"- 距离：{_format_distance(route.get('distance'))}",
            f"- 预计耗时：{_format_duration(route.get('duration'))}",
        ]
        if route.get("mode") == "driving" and route.get("cost_text"):
            lines.append(f"- 打车参考价：{route['cost_text']}")
        if route.get("mode") == "transit" and route.get("cost_text"):
            lines.append(f"- 票价参考：{route['cost_text']}")
        if route.get("walking_distance") not in (None, ""):
            lines.append(f"- 总步行距离：{_format_distance(route.get('walking_distance'))}")
        lines.extend(["", "### 逐步换乘"])
        _append_transit_step_lines(lines, steps)
        return "\n".join(lines)
    except ServiceError as exc:
        return f"路线规划失败：{exc}"
    except ValueError as exc:
        return f"路线规划参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"路线规划异常：{exc}"


@tool
def amap_city_route_plan(
    origin_city: str,
    destination_city: str,
    mode: str = "driving",
) -> str:
    """规划城市到城市的地图级路线参考。"""
    try:
        service = _get_amap_service()
        origin_loc, origin_display, origin_resolved_city = _resolve_location(origin_city, city_hint=origin_city)
        destination_loc, destination_display, destination_resolved_city = _resolve_location(
            destination_city,
            city_hint=destination_city,
        )

        route = _route_between(
            service=service,
            origin=origin_loc,
            destination=destination_loc,
            city=origin_resolved_city or origin_city,
            mode=mode,
        )

        lines = [
            "## 城市路线规划",
            f"- 出发城市：{origin_resolved_city or origin_city}",
            f"- 目的城市：{destination_resolved_city or destination_city}",
            f"- 出行方式：{_format_mode_label(route.get('mode') or mode)}",
            f"- 跨城驾车距离：{_format_distance(route.get('distance'))}",
            f"- 跨城驾车耗时：{_format_duration(route.get('duration'))}",
            f"- 说明：地图级路线参考，起终点分别按 {origin_display} 和 {destination_display} 处理。",
        ]
        if route.get("cost_text"):
            if route.get("mode") == "transit":
                lines.append(f"- 票价参考：{route['cost_text']}")
            else:
                lines.append(f"- 打车参考价：{route['cost_text']}")
        return "\n".join(lines)
    except ServiceError as exc:
        return f"城市路线规划失败：{exc}"
    except ValueError as exc:
        return f"城市路线规划参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"城市路线规划异常：{exc}"


@tool
def amap_search_nearby_food(
    center: str,
    city: str = "",
    radius: int = 3000,
    limit: int = 8,
) -> str:
    """按中心点查询周边美食。"""
    try:
        location, display, _ = _resolve_location(center, city_hint=city)
        payload = _get_amap_service().search_nearby_food(
            location=location,
            radius=min(max(radius, 300), 10000),
            page_size=min(max(limit, 1), 10),
        )
        items = payload.get("items") or []
        lines = [
            "## 周边美食推荐",
            f"- 中心点：{display}",
            f"- 搜索半径：{min(max(radius, 300), 10000)} m",
            f"- 命中总数：{payload.get('count') or 0}",
            "",
            "### 推荐列表",
        ]
        if not items:
            lines.append("附近没有找到合适的美食 POI。")
            return "\n".join(lines)

        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. **{item.get('name') or '未知美食'}**（{item.get('type') or '美食'}）")
            lines.append(
                f"   距离：{_format_distance(item.get('distance'))} | 地址：{item.get('address') or '未知'}"
            )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"周边美食搜索失败：{exc}"
    except ValueError as exc:
        return f"周边美食搜索参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"周边美食搜索异常：{exc}"


@tool
def amap_search_stays(
    center: str,
    city: str = "",
    radius: int = 5000,
    limit: int = 8,
    max_budget: float = 0,
    min_rating: float = 0,
    max_distance_m: int = 0,
    include_unknown_budget: bool = True,
    include_unknown_rating: bool = True,
) -> str:
    """按中心点查询周边酒店/民宿，并做简单筛选。"""
    try:
        location, display, _ = _resolve_location(center, city_hint=city)
        safe_radius = min(max(radius, 300), 15000)
        safe_limit = min(max(limit, 1), 12)
        payload = _get_amap_service().search_stays_with_filters(
            location=location,
            radius=safe_radius,
            limit=safe_limit,
            min_rating=min_rating if min_rating > 0 else None,
            max_budget=max_budget if max_budget > 0 else None,
            max_distance_m=max_distance_m if max_distance_m > 0 else None,
            include_unknown_budget=include_unknown_budget,
            include_unknown_rating=include_unknown_rating,
        )
        items = payload.get("items") or []
        lines = [
            "## 住宿推荐（酒店/民宿）",
            f"- 中心点：{display}",
            f"- 搜索半径：{safe_radius} m",
            f"- 筛选后数量：{payload.get('count', len(items))}/{payload.get('before_filter_count', len(items))}",
            (
                "- 筛选条件："
                f"预算上限 {_format_budget(max_budget if max_budget > 0 else None)} | "
                f"最低评分 {min_rating if min_rating > 0 else '不限'} | "
                f"最大距离 {max_distance_m if max_distance_m > 0 else '不限'}"
            ),
            "",
            "### 推荐列表",
        ]
        if not items:
            lines.append("没有找到符合条件的住宿候选。")
            return "\n".join(lines)

        for index, item in enumerate(items, start=1):
            budget_value, budget_source = _resolve_stay_budget(item)
            lines.append(f"{index}. **{item.get('name') or '未知住宿'}**（{item.get('type') or '住宿'}）")
            lines.append(
                f"   距离：{_format_distance(item.get('distance'))} | "
                f"评分：{_format_rating(item.get('rating'))} | "
                f"人均：{_format_budget(budget_value)}"
            )
            lines.append(f"   价格来源：{budget_source}")
            lines.append(
                f"   地址：{item.get('address') or '未知'} | 电话：{item.get('tel') or '未知'}"
            )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"住宿搜索失败：{exc}"
    except ValueError as exc:
        return f"住宿搜索参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"住宿搜索异常：{exc}"


@tool
def amap_plan_spot_routes(
    city: str,
    spots: str,
    mode: str = "driving",
) -> str:
    """串联多个景点，输出景点顺序和逐段交通。"""
    normalized_mode = (mode or "driving").strip().lower()
    if normalized_mode not in {"driving", "walking", "transit"}:
        return "景点串联路线的 mode 仅支持 driving、walking、transit。"

    spot_items = _parse_spot_sequence(spots)
    if len(spot_items) < 2:
        return "景点串联至少需要 2 个景点，请用逗号、顿号或 -> 分隔。"

    try:
        service = _get_amap_service()
        resolved_points: list[tuple[str, str, str]] = []
        for spot in spot_items:
            location, display, _ = _resolve_location(spot, city_hint=city)
            resolved_points.append((spot, display, location))

        optimized_points, optimization_note = _optimize_spot_order(
            service=service,
            resolved_points=resolved_points,
            city=city,
            mode=normalized_mode,
        )

        lines = [
            "## 景点串联路线",
            f"- 城市：{city}",
            f"- 出行方式：{_format_mode_label(normalized_mode)}",
            f"- 景点顺序：{' -> '.join(item[0] for item in optimized_points)}",
            f"- 原始顺序：{' -> '.join(spot_items)}",
            f"- 自动顺序优化：{optimization_note}",
            "",
            "### 路线总览",
            "| 段落 | 起点 | 终点 | 距离 | 耗时 |",
            "| --- | --- | --- | --- | --- |",
        ]

        leg_blocks: list[str] = []
        total_distance = 0
        total_duration = 0

        for index in range(len(optimized_points) - 1):
            origin_name, origin_display, origin_loc = optimized_points[index]
            destination_name, destination_display, destination_loc = optimized_points[index + 1]
            route = _route_between(
                service=service,
                origin=origin_loc,
                destination=destination_loc,
                city=city,
                mode=normalized_mode,
            )
            distance_text = _format_distance(route.get("distance"))
            duration_text = _format_duration(route.get("duration"))
            total_distance += max(_safe_int(route.get("distance"), default=0), 0)
            total_duration += max(_safe_int(route.get("duration"), default=0), 0)

            lines.append(
                f"| {index + 1} | {origin_display} | {destination_display} | {distance_text} | {duration_text} |"
            )

            steps = route.get("steps") or _build_fallback_steps(
                mode=route.get("mode") or normalized_mode,
                destination_name=destination_display,
                distance=route.get("distance"),
                duration=route.get("duration"),
            )
            block = [
                "",
                f"### 第 {index + 1} 段：{origin_display} -> {destination_display}",
                f"- 出行方式：{_format_mode_label(route.get('mode') or normalized_mode)}",
                f"- 距离：{distance_text}",
                f"- 耗时：{duration_text}",
            ]
            if route.get("cost_text"):
                block.append(f"- 票价参考：{route['cost_text']}")
            if route.get("walking_distance") not in (None, ""):
                block.append(f"- 总步行距离：{_format_distance(route.get('walking_distance'))}")
            _append_transit_step_lines(block, steps)
            leg_blocks.extend(block)

        lines.extend(
            [
                "",
                *leg_blocks,
                "",
                "### 汇总",
                f"- 总距离：{_format_distance(total_distance)}",
                f"- 总耗时：{_format_duration(total_duration)}",
                "- 说明：如遇景区限行、施工或实时拥堵，请以高德实时导航为准。",
            ]
        )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"景点串联路线规划失败：{exc}"
    except ValueError as exc:
        return f"景点串联路线规划参数错误：{exc}"
    except Exception as exc:  # pragma: no cover
        return f"景点串联路线规划异常：{exc}"
