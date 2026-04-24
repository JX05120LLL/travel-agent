"""高德地图工具集。

目标：
1. 给 Agent 提供可直接调用的地图能力（地理编码、POI、路线）。
2. 兼容“地址文本”与“经纬度”两种输入，减少调用方心智负担。
"""

from __future__ import annotations

from itertools import permutations
import re

from langchain_core.tools import tool

from services.amap_service import AmapService
from services.errors import ServiceError

_COORD_PATTERN = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
_amap_service: AmapService | None = None


def _get_amap_service() -> AmapService:
    """惰性初始化高德服务，避免模块导入时即触发配置校验。"""
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service


def _is_coordinate(value: str) -> bool:
    return bool(_COORD_PATTERN.match((value or "").strip()))


def _format_distance(distance_text: str | None) -> str:
    if not distance_text:
        return "未知"
    try:
        distance = int(float(distance_text))
    except (TypeError, ValueError):
        return str(distance_text)
    if distance >= 1000:
        return f"{distance / 1000:.1f} km"
    return f"{distance} m"


def _format_duration(duration_text: str | None) -> str:
    if not duration_text:
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
    return None, "高德未返回"


def _safe_int(value: str | int | float | None, default: int = 10**9) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_city_name(city_name: str) -> str:
    return (city_name or "").strip().replace("市", "")


def _merge_unique_pois(*groups: list[dict]) -> list[dict]:
    """按 id/location 去重合并 POI。"""
    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for group in groups:
        for item in group:
            key = (
                str(item.get("id") or item.get("name") or ""),
                str(item.get("location") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    merged.sort(key=lambda x: _safe_int(x.get("distance")))
    return merged


def _parse_spot_sequence(spots: str) -> list[str]:
    raw = (spots or "").strip()
    if not raw:
        return []
    normalized = (
        raw.replace("->", "，")
        .replace("→", "，")
        .replace(";", "，")
        .replace("；", "，")
        .replace(",", "，")
    )
    items = []
    seen = set()
    for part in normalized.split("，"):
        name = part.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        items.append(name)
    return items


def _format_mode_label(mode: str) -> str:
    mapping = {
        "driving": "驾车",
        "walking": "步行",
        "transit": "公交/地铁",
    }
    return mapping.get(mode, mode)


def _format_transit_step_type(step_type: str | None) -> str:
    mapping = {
        "walk": "步行",
        "metro": "地铁",
        "bus": "公交",
        "railway": "铁路",
        "other": "出行",
    }
    text = (step_type or "").strip().lower()
    return mapping.get(text, step_type or "其他")


def _format_cost_text(value: str | int | float | None) -> str | None:
    if value in (None, "", []):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if amount.is_integer():
        return f"{int(amount)} 元"
    return f"{amount:.1f} 元"


def _extract_metric(primary: dict, field: str, *, default: int = 0) -> int:
    value = primary.get(f"{field}_value")
    if isinstance(value, (int, float)):
        return int(value)
    parsed = _safe_int(primary.get(field), default=default)
    return max(parsed, 0) if parsed != default else default


def _build_fallback_leg_steps(
    *,
    mode: str,
    destination: str,
    distance: str | None,
    duration: str | None,
) -> list[dict]:
    if mode == "walking":
        instruction = f"步行前往 {destination}"
        step_type = "walk"
    else:
        instruction = f"驾车前往 {destination}"
        step_type = "other"
    return [
        {
            "type": step_type,
            "instruction": instruction,
            "distance": distance,
            "duration": duration,
        }
    ]


def _append_transit_step_lines(lines: list[str], steps: list[dict]) -> None:
    for index, step in enumerate(steps, start=1):
        instruction = step.get("instruction") or "前往下一段"
        lines.append(f"{index}. {instruction}")
        lines.append(f"   - 类型：{_format_transit_step_type(step.get('type'))}")
        if step.get("line"):
            lines.append(f"   - 线路：{step.get('line')}")
        if step.get("departure_stop"):
            lines.append(f"   - 上车站：{step.get('departure_stop')}")
        if step.get("arrival_stop"):
            lines.append(f"   - 下车站：{step.get('arrival_stop')}")
        if step.get("via_num") not in (None, ""):
            lines.append(f"   - 站数：{step.get('via_num')}")
        if step.get("distance") not in (None, ""):
            lines.append(f"   - 距离：{_format_distance(step.get('distance'))}")
        if step.get("duration") not in (None, ""):
            lines.append(f"   - 预计耗时：{_format_duration(step.get('duration'))}")
        if step.get("ticket_cost_text"):
            lines.append(f"   - 票价参考：{step.get('ticket_cost_text')}")
        if step.get("destination_name"):
            lines.append(f"   - 到达点：{step.get('destination_name')}")
        if step.get("entrance"):
            lines.append(f"   - 入口：{step.get('entrance')}")
        if step.get("exit"):
            lines.append(f"   - 出口：{step.get('exit')}")


def _get_leg_route_result(
    *,
    service: AmapService,
    origin: str,
    destination: str,
    city: str,
    mode: str,
    cache: dict[tuple[str, str, str, str], tuple[dict, dict]],
) -> tuple[dict, dict]:
    key = (origin, destination, mode, city)
    cached = cache.get(key)
    if cached is not None:
        return cached

    if mode == "walking":
        result = service.route_walking(origin=origin, destination=destination)
        primary = result.get("primary_path") or {}
    elif mode == "driving":
        result = service.route_driving(origin=origin, destination=destination)
        primary = result.get("primary_path") or {}
    else:
        result = service.route_transit(
            origin=origin,
            destination=destination,
            city=city,
            cityd=city,
        )
        primary = result.get("primary_transit") or {}

    cache[key] = (result, primary)
    return result, primary


def _optimize_spot_order(
    *,
    service: AmapService,
    resolved_points: list[tuple[str, str, str]],
    city: str,
    mode: str,
    cache: dict[tuple[str, str, str, str], tuple[dict, dict]],
) -> tuple[list[tuple[str, str, str]], str | None]:
    if len(resolved_points) <= 2:
        return resolved_points, None

    start_point = resolved_points[0]
    remaining = resolved_points[1:]
    original_order = list(resolved_points)

    def plan_cost(sequence: tuple[tuple[str, str, str], ...]) -> tuple[int, int]:
        duration_total = 0
        distance_total = 0
        ordered = (start_point, *sequence)
        for index in range(len(ordered) - 1):
            _, primary = _get_leg_route_result(
                service=service,
                origin=ordered[index][2],
                destination=ordered[index + 1][2],
                city=city,
                mode=mode,
                cache=cache,
            )
            duration_total += _extract_metric(primary, "duration", default=10**9)
            distance_total += _extract_metric(primary, "distance", default=10**9)
        return duration_total, distance_total

    if len(resolved_points) <= 6:
        best_sequence = min(
            permutations(remaining),
            key=plan_cost,
        )
        optimized = [start_point, *best_sequence]
    else:
        optimized = [start_point]
        unvisited = list(remaining)
        while unvisited:
            current = optimized[-1]
            next_point = min(
                unvisited,
                key=lambda point: (
                    _extract_metric(
                        _get_leg_route_result(
                            service=service,
                            origin=current[2],
                            destination=point[2],
                            city=city,
                            mode=mode,
                            cache=cache,
                        )[1],
                        "duration",
                        default=10**9,
                    ),
                    _extract_metric(
                        _get_leg_route_result(
                            service=service,
                            origin=current[2],
                            destination=point[2],
                            city=city,
                            mode=mode,
                            cache=cache,
                        )[1],
                        "distance",
                        default=10**9,
                    ),
                ),
            )
            optimized.append(next_point)
            unvisited.remove(next_point)

    optimized_names = [item[0] for item in optimized]
    original_names = [item[0] for item in original_order]
    if optimized_names == original_names:
        return optimized, "已评估，保持原顺序（固定首点）"
    return optimized, f"已启用（固定首点：{start_point[0]}）"


def _resolve_location(
    value: str,
    *,
    city_hint: str | None = None,
) -> tuple[str, str, str | None]:
    """将输入解析为经纬度。

    返回：
    - location: lng,lat
    - display: 解析后的展示文本
    - city_name: 解析到的城市（可能为空）
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("地点不能为空。")

    if _is_coordinate(raw):
        return raw, raw, (city_hint or "").strip() or None

    service = _get_amap_service()
    geo = service.geocode(address=raw, city=(city_hint or "").strip() or None)
    primary = geo.get("primary") or {}
    location = (primary.get("location") or "").strip()
    if not location:
        raise ValueError(f"无法解析地点：{raw}")
    display = primary.get("formatted_address") or raw
    resolved_city = primary.get("city") or (city_hint or "").strip() or None
    return location, display, resolved_city


@tool
def amap_geocode(address: str, city: str = "") -> str:
    """高德地理编码：地址转经纬度。

    适用场景：
    - 用户给的是“杭州西湖”“北京南站”这类地址名称
    - 后续要做路线规划前，先转坐标
    """
    try:
        service = _get_amap_service()
        result = service.geocode(address=address, city=city or None)
        primary = result.get("primary")
        if not primary:
            return f"未找到地址：{address}"

        return (
            f"【高德地理编码】\n"
            f"地址：{primary.get('formatted_address') or address}\n"
            f"坐标：{primary.get('location')}\n"
            f"行政区：{primary.get('province', '')}{primary.get('city', '')}{primary.get('district', '')}\n"
            f"匹配数：{result.get('count', 0)}"
        )
    except ServiceError as exc:
        return f"高德地理编码失败：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"高德地理编码异常：{exc}"


@tool
def amap_search_poi(keywords: str, city: str = "", page_size: int = 5) -> str:
    """高德 POI 搜索。

    适用场景：
    - 查询某城市景点/商圈/车站/酒店
    - 给行程补充候选点位
    """
    safe_page_size = min(max(page_size, 1), 10)
    try:
        service = _get_amap_service()
        result = service.search_poi(
            keywords=keywords,
            city=city or None,
            page=1,
            page_size=safe_page_size,
        )
        items = result.get("items") or []
        if not items:
            return f"【高德POI搜索】\n关键词：{keywords}\n未找到结果。"

        lines = [
            "【高德POI搜索】",
            f"关键词：{keywords}",
            f"城市：{(city or '不限')}",
            f"命中总数：{result.get('count', 0)}",
            "候选点位：",
        ]
        for idx, item in enumerate(items[:safe_page_size], start=1):
            lines.append(
                f"{idx}. {item.get('name')}（{item.get('type') or '类型未知'}）"
            )
            lines.append(
                f"   地址：{item.get('address') or '未知'}；坐标：{item.get('location') or '未知'}"
            )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"高德POI搜索失败：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"高德POI搜索异常：{exc}"


@tool
def amap_route_plan(
    origin: str,
    destination: str,
    mode: str = "driving",
    city: str = "",
    strategy: int = 0,
) -> str:
    """高德路线规划。

    参数说明：
    - origin / destination：支持“地址文本”或“lng,lat”
    - mode：driving / walking / transit
    - city：公交模式建议提供城市名（若为空会尝试从地点解析结果推断）
    """
    mode_normalized = (mode or "driving").strip().lower()
    if mode_normalized not in {"driving", "walking", "transit"}:
        return "路线模式不支持，请使用 driving / walking / transit。"

    try:
        origin_loc, origin_display, origin_city = _resolve_location(origin, city_hint=city)
        destination_loc, destination_display, destination_city = _resolve_location(
            destination,
            city_hint=city,
        )

        service = _get_amap_service()
        lines = [
            "## 路线规划",
            f"- 起点：{origin_display}",
            f"- 终点：{destination_display}",
            f"- 出行方式：{_format_mode_label(mode_normalized)}",
        ]

        if mode_normalized == "walking":
            result = service.route_walking(origin=origin_loc, destination=destination_loc)
            primary = result.get("primary_path") or {}
            lines.append(f"距离：{_format_distance(primary.get('distance'))}")
            lines.append(f"预计耗时：{_format_duration(primary.get('duration'))}")
            return "\n".join(lines)

        if mode_normalized == "driving":
            result = service.route_driving(
                origin=origin_loc,
                destination=destination_loc,
                strategy=strategy,
            )
            primary = result.get("primary_path") or {}
            lines.append(f"距离：{_format_distance(primary.get('distance'))}")
            lines.append(f"预计耗时：{_format_duration(primary.get('duration'))}")
            if result.get("taxi_cost"):
                lines.append(f"打车参考价：{result.get('taxi_cost')} 元")
            return "\n".join(lines)

        transit_city = (city or origin_city or destination_city or "").strip()
        if not transit_city:
            return (
                "公交路线规划需要 city 参数。请补充城市名，例如 city=杭州。"
            )

        result = service.route_transit(
            origin=origin_loc,
            destination=destination_loc,
            city=transit_city,
            strategy=strategy if strategy in {0, 1, 2, 3, 4, 5} else 0,
        )
        primary = result.get("primary_transit") or {}
        lines.append(f"城市：{transit_city}")
        lines.append(f"预计耗时：{_format_duration(primary.get('duration'))}")
        if primary.get("distance") not in (None, ""):
            lines.append(f"距离：{_format_distance(primary.get('distance'))}")
        lines.append(
            f"总步行距离：{_format_distance(primary.get('walking_distance'))}"
        )
        cost_text = primary.get("cost_text") or _format_cost_text(primary.get("cost"))
        if cost_text:
            lines.append(f"票价参考：{cost_text}")
        steps = primary.get("steps") or []
        if steps:
            lines.extend(["", "### 逐步换乘"])
            _append_transit_step_lines(lines, steps)
        return "\n".join(lines)
    except ServiceError as exc:
        return f"高德路线规划失败：{exc}"
    except ValueError as exc:
        return f"高德路线规划参数错误：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"高德路线规划异常：{exc}"


@tool
def amap_city_route_plan(
    origin_city: str,
    destination_city: str,
    mode: str = "driving",
    strategy: int = 0,
) -> str:
    """城市到城市路线规划。

    适用场景：
    - 用户问“杭州到上海怎么走”“北京到天津路线建议”
    - 需要快速给出城市级路线耗时与距离参考
    """
    mode_normalized = (mode or "driving").strip().lower()
    if mode_normalized not in {"driving", "walking", "transit"}:
        return "路线模式不支持，请使用 driving / walking / transit。"

    try:
        service = _get_amap_service()
        origin_loc, origin_display, _ = _resolve_location(
            origin_city,
            city_hint=origin_city,
        )
        destination_loc, destination_display, _ = _resolve_location(
            destination_city,
            city_hint=destination_city,
        )
        origin_city_norm = _normalize_city_name(origin_city)
        destination_city_norm = _normalize_city_name(destination_city)

        lines = [
            "## 城市路线规划",
            f"- 出发城市：{origin_display}",
            f"- 目的城市：{destination_display}",
            f"- 出行方式：{_format_mode_label(mode_normalized)}",
        ]

        if mode_normalized == "walking":
            result = service.route_walking(
                origin=origin_loc,
                destination=destination_loc,
            )
            primary = result.get("primary_path") or {}
            lines.append(f"距离：{_format_distance(primary.get('distance'))}")
            lines.append(f"预计耗时：{_format_duration(primary.get('duration'))}")
            return "\n".join(lines)

        if mode_normalized == "driving":
            result = service.route_driving(
                origin=origin_loc,
                destination=destination_loc,
                strategy=strategy,
            )
            primary = result.get("primary_path") or {}
            lines.append(f"距离：{_format_distance(primary.get('distance'))}")
            lines.append(f"预计耗时：{_format_duration(primary.get('duration'))}")
            if result.get("taxi_cost"):
                lines.append(f"打车参考价：{result.get('taxi_cost')} 元")
            return "\n".join(lines)

        if origin_city_norm != destination_city_norm:
            lines.append(
                "说明：高德公交/地铁路线主要面向同城。跨城场景已自动给出驾车方案参考。"
            )
            driving = service.route_driving(
                origin=origin_loc,
                destination=destination_loc,
                strategy=strategy,
            )
            primary = driving.get("primary_path") or {}
            lines.append(f"跨城驾车距离：{_format_distance(primary.get('distance'))}")
            lines.append(f"跨城驾车耗时：{_format_duration(primary.get('duration'))}")
            return "\n".join(lines)

        transit = service.route_transit(
            origin=origin_loc,
            destination=destination_loc,
            city=origin_city,
            cityd=destination_city,
            strategy=strategy if strategy in {0, 1, 2, 3, 4, 5} else 0,
        )
        primary = transit.get("primary_transit") or {}
        lines.append(f"预计耗时：{_format_duration(primary.get('duration'))}")
        if primary.get("distance") not in (None, ""):
            lines.append(f"距离：{_format_distance(primary.get('distance'))}")
        lines.append(f"总步行距离：{_format_distance(primary.get('walking_distance'))}")
        cost_text = primary.get("cost_text") or _format_cost_text(primary.get("cost"))
        if cost_text:
            lines.append(f"票价参考：{cost_text}")
        steps = primary.get("steps") or []
        if steps:
            lines.extend(["", "### 逐步换乘"])
            _append_transit_step_lines(lines, steps)
        return "\n".join(lines)
    except ServiceError as exc:
        return f"城市路线规划失败：{exc}"
    except ValueError as exc:
        return f"城市路线规划参数错误：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"城市路线规划异常：{exc}"


@tool
def amap_search_nearby_food(
    center: str,
    city: str = "",
    radius: int = 3000,
    limit: int = 6,
) -> str:
    """周边美食检索。

    参数：
    - center：中心点，支持地址文本或 lng,lat
    - city：中心点是地址文本时可选，用于提高解析精度
    """
    safe_limit = min(max(limit, 1), 10)
    safe_radius = min(max(radius, 100), 10000)
    try:
        location, display, _ = _resolve_location(center, city_hint=city)
        service = _get_amap_service()
        result = service.search_nearby_food(
            location=location,
            radius=safe_radius,
            page=1,
            page_size=safe_limit,
        )
        items = result.get("items") or []
        if not items:
            return (
                "【高德周边美食】\n"
                f"中心点：{display}\n"
                f"半径：{safe_radius} 米\n"
                "未找到美食相关点位。"
            )

        lines = [
            "## 周边美食推荐",
            f"- 中心点：{display}",
            f"- 检索半径：{safe_radius} 米",
            f"- 命中总数：{result.get('count', 0)}",
            "",
            "### 推荐列表",
        ]
        for idx, item in enumerate(items[:safe_limit], start=1):
            lines.append(
                f"{idx}. **{item.get('name')}**（{item.get('type') or '餐饮'}）"
            )
            lines.append(
                f"   距离：{_format_distance(item.get('distance'))}｜"
                f"地址：{item.get('address') or '未知'}"
            )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"周边美食检索失败：{exc}"
    except ValueError as exc:
        return f"周边美食检索参数错误：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"周边美食检索异常：{exc}"


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
    """酒店/民宿查询。

    说明：
    - 高德支持住宿类 POI 检索（酒店、宾馆、民宿等），这里会合并“酒店”和“民宿”两类结果。
    - 支持筛选：预算、评分、距离景点。
    """
    safe_limit = min(max(limit, 1), 12)
    safe_radius = min(max(radius, 300), 15000)
    try:
        location, display, _ = _resolve_location(center, city_hint=city)
        service = _get_amap_service()
        effective_min_rating = min_rating if min_rating > 0 else None
        effective_max_budget = max_budget if max_budget > 0 else None
        effective_max_distance = max_distance_m if max_distance_m > 0 else None

        filtered_result = service.search_stays_with_filters(
            location=location,
            radius=safe_radius,
            limit=safe_limit,
            min_rating=effective_min_rating,
            max_budget=effective_max_budget,
            max_distance_m=effective_max_distance,
            include_unknown_budget=include_unknown_budget,
            include_unknown_rating=include_unknown_rating,
        )
        merged = filtered_result.get("items") or []
        if not merged:
            return (
                "【高德住宿检索】\n"
                f"中心点：{display}\n"
                f"半径：{safe_radius} 米\n"
                "未找到酒店/民宿。"
            )

        lines = [
            "## 住宿推荐（酒店/民宿）",
            f"- 中心点：{display}",
            f"- 检索半径：{safe_radius} 米",
            (
                f"- 筛选后数量：{filtered_result.get('count', len(merged))}/"
                f"{filtered_result.get('before_filter_count', len(merged))}"
            ),
            (
                "- 筛选条件："
                f"预算≤{_format_budget(effective_max_budget)}，"
                f"评分≥{effective_min_rating if effective_min_rating is not None else '不限'}，"
                f"距离≤{effective_max_distance if effective_max_distance is not None else '不限'} 米"
            ),
            "",
            "### 推荐列表",
        ]
        for idx, item in enumerate(merged, start=1):
            budget_value, budget_source = _resolve_stay_budget(item)
            lines.append(
                f"{idx}. **{item.get('name')}**（{item.get('type') or '住宿'}）"
            )
            lines.append(
                f"   距离：{_format_distance(item.get('distance'))}｜"
                f"评分：{item.get('rating') if item.get('rating') is not None else '未知'}｜"
                f"人均：{_format_budget(budget_value)}"
            )
            lines.append(f"   价格来源：{budget_source}")
            lines.append(
                f"   地址：{item.get('address') or '未知'}｜电话：{item.get('tel') or '未知'}"
            )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"住宿检索失败：{exc}"
    except ValueError as exc:
        return f"住宿检索参数错误：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"住宿检索异常：{exc}"


@tool
def amap_plan_spot_routes(
    city: str,
    spots: str,
    mode: str = "driving",
) -> str:
    """景点串联路线规划（支持自动顺序优化）。

    参数：
    - city：城市名
    - spots：景点序列，示例：西湖, 灵隐寺, 河坊街
    - mode：driving / walking / transit
    """
    mode_normalized = (mode or "driving").strip().lower()
    if mode_normalized not in {"driving", "walking", "transit"}:
        return "路线模式不支持，请使用 driving / walking / transit。"

    spot_items = _parse_spot_sequence(spots)
    if len(spot_items) < 2:
        return "景点串联至少需要 2 个点位，请用逗号分隔，例如：西湖, 灵隐寺。"

    try:
        service = _get_amap_service()
        resolved_points = []
        for spot in spot_items:
            loc, display, _ = _resolve_location(spot, city_hint=city)
            resolved_points.append((spot, display, loc))

        route_cache: dict[tuple[str, str, str, str], tuple[dict, dict]] = {}
        optimized_points, optimization_note = _optimize_spot_order(
            service=service,
            resolved_points=resolved_points,
            city=city,
            mode=mode_normalized,
            cache=route_cache,
        )

        total_distance = 0
        total_duration = 0
        detailed_leg_blocks: list[str] = []
        lines = [
            "## 景点串联路线",
            f"- 城市：{city}",
            f"- 出行方式：{_format_mode_label(mode_normalized)}",
            f"- 景点顺序：{' -> '.join(point[0] for point in optimized_points)}",
        ]
        if len(optimized_points) > 2:
            lines.extend(
                [
                    f"- 原始顺序：{' -> '.join(spot_items)}",
                    f"- 自动顺序优化：{optimization_note or '未启用'}",
                ]
            )
        lines.extend(
            [
                "",
                "### 分段明细",
                "| 段落 | 起点 | 终点 | 距离 | 耗时 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )

        for index in range(len(optimized_points) - 1):
            _from_name, from_display, from_loc = optimized_points[index]
            _to_name, to_display, to_loc = optimized_points[index + 1]
            _, primary = _get_leg_route_result(
                service=service,
                origin=from_loc,
                destination=to_loc,
                city=city,
                mode=mode_normalized,
                cache=route_cache,
            )

            distance = _extract_metric(primary, "distance")
            duration = _extract_metric(primary, "duration")
            total_distance += max(distance, 0)
            total_duration += max(duration, 0)

            lines.append(
                f"| {index + 1} | {from_display} | {to_display} | "
                f"{_format_distance(primary.get('distance'))} | "
                f"{_format_duration(primary.get('duration'))} |"
            )

            leg_cost_text = primary.get("cost_text") or _format_cost_text(primary.get("cost"))
            leg_steps = primary.get("steps") or _build_fallback_leg_steps(
                mode=mode_normalized,
                destination=to_display,
                distance=primary.get("distance"),
                duration=primary.get("duration"),
            )
            leg_lines = [
                "",
                f"### 第 {index + 1} 段：{from_display} -> {to_display}",
                f"- 出行方式：{_format_mode_label(mode_normalized)}",
                f"- 距离：{_format_distance(primary.get('distance'))}",
                f"- 耗时：{_format_duration(primary.get('duration'))}",
            ]
            if primary.get("walking_distance") not in (None, ""):
                leg_lines.append(
                    f"- 总步行距离：{_format_distance(primary.get('walking_distance'))}"
                )
            if leg_cost_text:
                leg_lines.append(f"- 票价参考：{leg_cost_text}")
            _append_transit_step_lines(leg_lines, leg_steps)
            detailed_leg_blocks.extend(leg_lines)

        lines.extend(
            [
                "",
                *detailed_leg_blocks,
                "",
                "### 总体估算",
                f"- 总距离：{_format_distance(str(total_distance))}",
                f"- 总耗时：{_format_duration(str(total_duration))}",
                "- 说明：这是分段通勤总和，未包含景点停留时间。",
            ]
        )
        return "\n".join(lines)
    except ServiceError as exc:
        return f"景点串联路线规划失败：{exc}"
    except ValueError as exc:
        return f"景点串联路线规划参数错误：{exc}"
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"景点串联路线规划异常：{exc}"
