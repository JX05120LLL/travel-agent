"""Trip 成品行程单编排服务。"""

from __future__ import annotations

from typing import Any


def _strip(value: Any) -> str:
    return str(value or "").strip()


def _first(items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict):
            return item
    return None


class TripDocumentService:
    """把结构化结果编排成前端与导出共用的成品行程单。"""

    PERIOD_LABELS = {
        "morning": "上午",
        "afternoon": "下午",
        "evening": "晚上",
    }

    @classmethod
    def build_delivery_payload(cls, *, trip, structured_context: dict | None) -> dict[str, Any]:
        context = structured_context if isinstance(structured_context, dict) else {}
        arrival = cls._extract_arrival(context)
        stay = cls._extract_stay(context)
        map_preview = cls._extract_map_preview(context)
        budget = cls._extract_assistant_section(context, "budget")
        notes = cls._extract_assistant_section(context, "notes")
        assumptions = cls._extract_assistant_section(context, "assumptions")
        reasons = cls._extract_assistant_section(context, "reasons")
        booking_notices = cls._extract_booking_notices(arrival, stay)
        daily_itinerary = cls._build_daily_itinerary(
            trip,
            arrival=arrival,
            stay=stay,
            structured_context=context,
        )
        food = cls._extract_food_summary(trip)
        overview = cls._build_overview(
            trip=trip,
            arrival=arrival,
            stay=stay,
            budget=budget,
            reasons=reasons,
        )

        return {
            "overview": overview,
            "arrival": arrival,
            "stay": stay,
            "map_preview": map_preview,
            "daily_itinerary": daily_itinerary,
            "food": food,
            "budget": budget,
            "notes": notes,
            "assumptions": assumptions,
            "recommendation_reasons": reasons,
            "booking_notices": booking_notices,
        }

    @classmethod
    def build_document_markdown(cls, payload: dict[str, Any]) -> str:
        overview = payload.get("overview") or {}
        arrival = payload.get("arrival") or {}
        stay = payload.get("stay") or {}
        map_preview = payload.get("map_preview") or {}
        daily_itinerary = payload.get("daily_itinerary") or []
        food = payload.get("food") or {}
        budget = payload.get("budget") or {}
        notes = payload.get("notes") or {}
        assumptions = payload.get("assumptions") or {}
        reasons = payload.get("recommendation_reasons") or {}
        booking_notices = payload.get("booking_notices") or []

        lines = [
            f"# {overview.get('title') or '旅行方案'}",
        ]
        if overview.get("summary"):
            lines.extend(["", overview["summary"]])

        if reasons.get("items"):
            lines.extend(["", "## 推荐理由"])
            lines.extend(f"- {item}" for item in reasons["items"] if _strip(item))

        if arrival:
            lines.extend(["", "## 到达方式"])
            lines.append(f"- 推荐方式：{arrival.get('recommended_mode') or '待补充'}")
            lines.append(
                f"- 跨城路线：{arrival.get('origin_city') or '出发地待补充'} -> "
                f"{arrival.get('destination_city') or '目的地待补充'}"
            )
            if arrival.get("duration_text"):
                lines.append(f"- 预计耗时：{arrival.get('duration_text')}")
            if arrival.get("price_text"):
                lines.append(f"- 票价参考：{arrival.get('price_text')}")
            if arrival.get("fetched_at"):
                lines.append(f"- 数据时效：{arrival.get('fetched_at')}")
            if arrival.get("summary"):
                lines.append(f"- 到达建议：{arrival.get('summary')}")
            top_candidate = _first(arrival.get("candidates"))
            if top_candidate:
                lines.append(
                    f"- 推荐车次：{top_candidate.get('train_no') or '待补充'}"
                    + (
                        f"（{top_candidate.get('depart_station') or ''}"
                        f" -> {top_candidate.get('arrive_station') or ''}）"
                        if top_candidate.get("depart_station") or top_candidate.get("arrive_station")
                        else ""
                    )
                )
                if top_candidate.get("depart_time") or top_candidate.get("arrive_time"):
                    lines.append(
                        f"- 发到时间：{top_candidate.get('depart_time') or '待补充'} -> "
                        f"{top_candidate.get('arrive_time') or '待补充'}"
                    )
                if top_candidate.get("availability_text"):
                    lines.append(f"- 余票参考：{top_candidate.get('availability_text')}")
                if top_candidate.get("seat_summary"):
                    lines.append(f"- 席位参考：{top_candidate.get('seat_summary')}")
            candidates = arrival.get("candidates") or []
            if isinstance(candidates, list) and len(candidates) > 1:
                lines.append("- 候选车次：")
                for candidate in candidates[1:4]:
                    if not isinstance(candidate, dict):
                        continue
                    option_parts = [
                        candidate.get("train_no"),
                        (
                            f"{candidate.get('depart_station') or '出发站待补充'} -> "
                            f"{candidate.get('arrive_station') or '到达站待补充'}"
                        ),
                        (
                            f"{candidate.get('depart_time') or '待补充'} -> "
                            f"{candidate.get('arrive_time') or '待补充'}"
                        )
                        if candidate.get("depart_time") or candidate.get("arrive_time")
                        else None,
                        candidate.get("price_text"),
                        candidate.get("availability_text"),
                    ]
                    lines.append("  - " + "｜".join(str(part) for part in option_parts if _strip(part)))
            if arrival.get("official_notice"):
                notice = arrival["official_notice"]
                lines.append(f"- 官方提醒：{notice.get('notice')}")

        if map_preview:
            lines.extend(["", "## 地图导航"])
            if map_preview.get("title"):
                lines.append(f"- 导航卡片：{map_preview.get('title')}")
            if map_preview.get("city"):
                lines.append(f"- 覆盖城市：{map_preview.get('city')}")
            markers = map_preview.get("markers") or []
            if markers:
                lines.append("- 关键点位：")
                for marker in markers[:6]:
                    if not isinstance(marker, dict):
                        continue
                    marker_name = marker.get("name") or "点位"
                    marker_location = marker.get("location") or "坐标待补充"
                    lines.append(f"  - {marker_name}（{marker_location}）")
            if map_preview.get("personal_map_open_url") or map_preview.get("personal_map_url"):
                lines.append(f"- 专属地图预览：{map_preview.get('personal_map_open_url') or map_preview.get('personal_map_url')}")
            if (
                map_preview.get("personal_map_url")
                and map_preview.get("personal_map_open_url")
                and map_preview.get("personal_map_url") != map_preview.get("personal_map_open_url")
            ):
                lines.append(f"- 手机端打开高德 App：{map_preview.get('personal_map_url')}")
            if map_preview.get("official_map_url"):
                lines.append(f"- 打开高德地图：{map_preview.get('official_map_url')}")
            if map_preview.get("navigation_url"):
                lines.append(f"- 导航前往酒店/首景点：{map_preview.get('navigation_url')}")
            if map_preview.get("degraded_reason"):
                lines.append(f"- 地图降级说明：{map_preview.get('degraded_reason')}")

        if daily_itinerary:
            lines.extend(["", "## 每日行程"])
            for day in daily_itinerary:
                day_title = _strip(day.get("title")) or (
                    "Day 0 到达日"
                    if day.get("day_type") == "arrival"
                    else f"Day {day.get('day_no') or ''}"
                )
                lines.extend(["", f"### {day_title}"])
                if day.get("summary"):
                    lines.append(f"- 摘要：{day.get('summary')}")
                if day.get("weather"):
                    lines.append(f"- 天气：{day.get('weather')}")
                for period in day.get("periods") or []:
                    lines.append(f"- {period.get('label')}")
                    for block in period.get("blocks") or []:
                        title = block.get("title") or "行程安排"
                        lines.append(f"  - {title}")
                        if block.get("transport"):
                            lines.append(f"    - 交通：{block.get('transport')}")
                        if block.get("activity"):
                            lines.append(f"    - 玩法：{block.get('activity')}")
                        if block.get("food"):
                            lines.append(f"    - 美食：{block.get('food')}")
                        if block.get("note"):
                            lines.append(f"    - 说明：{block.get('note')}")

        if stay:
            lines.extend(["", "## 酒店推荐"])
            if stay.get("summary"):
                lines.append(f"- 主结论：{stay.get('summary')}")
            primary = _first(stay.get("items"))
            if primary:
                lines.append(f"- 主推住宿：{primary.get('name') or '待补充'}")
                lines.append(f"- 片区：{primary.get('片区') or primary.get('district') or '待补充'}")
                if primary.get("价格") or primary.get("price_text"):
                    lines.append(f"- 价格：{primary.get('价格') or primary.get('price_text')}")
                if primary.get("价格来源") or primary.get("price_source_label"):
                    lines.append(
                        f"- 价格来源：{primary.get('价格来源') or primary.get('price_source_label')}"
                    )
                if stay.get("fetched_at"):
                    lines.append(f"- 数据时效：{stay.get('fetched_at')}")
                if primary.get("房型摘要") or primary.get("room_summary"):
                    lines.append(f"- 房型摘要：{primary.get('房型摘要') or primary.get('room_summary')}")
                if primary.get("预订链接") or primary.get("booking_url"):
                    lines.append(f"- 预订链接：{primary.get('预订链接') or primary.get('booking_url')}")

        if food.get("summary"):
            lines.extend(["", "## 美食推荐", f"- {food.get('summary')}"])
        if food.get("items"):
            lines.extend(f"- {item}" for item in food["items"] if _strip(item))

        if budget.get("summary") or budget.get("items"):
            lines.extend(["", "## 预算汇总"])
            if budget.get("summary"):
                lines.append(f"- {budget.get('summary')}")
            lines.extend(f"- {item}" for item in budget.get("items") or [] if _strip(item))

        if notes.get("items"):
            lines.extend(["", "## 注意事项"])
            lines.extend(f"- {item}" for item in notes["items"] if _strip(item))

        if assumptions.get("items"):
            lines.extend(["", "## 本次假设"])
            lines.extend(f"- {item}" for item in assumptions["items"] if _strip(item))

        if booking_notices:
            lines.extend(["", "## 预订与出票提醒"])
            for notice in booking_notices:
                if isinstance(notice, dict):
                    lines.append(f"- {notice.get('notice') or '请以下单页与官方渠道为准。'}")
                    if notice.get("website_url"):
                        lines.append(f"  - 官网：{notice.get('website_url')}")
                    if notice.get("app_url"):
                        lines.append(f"  - App：{notice.get('app_url')}")
                elif _strip(notice):
                    lines.append(f"- {notice}")

        return "\n".join(lines).strip()

    @classmethod
    def build_price_confidence_summary(cls, payload: dict[str, Any]) -> dict[str, Any]:
        arrival = payload.get("arrival") or {}
        stay = payload.get("stay") or {}
        stay_primary = _first(stay.get("items"))
        return {
            "hotel_price_status": stay.get("price_status") or "missing",
            "hotel_price_source": (
                stay_primary.get("价格来源")
                if isinstance(stay_primary, dict)
                else None
            ),
            "rail_ticket_status": arrival.get("ticket_status") or "reference",
            "rail_data_source": arrival.get("data_source") or "unknown",
        }

    @classmethod
    def _build_overview(
        cls,
        *,
        trip,
        arrival: dict[str, Any],
        stay: dict[str, Any],
        budget: dict[str, Any],
        reasons: dict[str, Any],
    ) -> dict[str, Any]:
        summary_parts = [
            _strip(getattr(trip, "summary", None)),
            _strip(reasons.get("summary")),
            _strip(arrival.get("summary")),
            _strip(stay.get("summary")),
            _strip(budget.get("summary")),
        ]
        summary = " ".join(part for part in summary_parts if part)
        return {
            "title": getattr(trip, "title", None) or "旅行方案",
            "summary": summary,
            "primary_destination": getattr(trip, "primary_destination", None),
            "total_days": getattr(trip, "total_days", None),
            "trip_status": getattr(trip, "status", None),
        }

    @classmethod
    def _extract_arrival(cls, structured_context: dict[str, Any]) -> dict[str, Any]:
        railway = structured_context.get("railway12306")
        if not isinstance(railway, dict):
            return {}
        arrivals = railway.get("arrivals")
        return _first(arrivals) or {}

    @classmethod
    def _extract_stay(cls, structured_context: dict[str, Any]) -> dict[str, Any]:
        hotel = structured_context.get("hotel_accommodation")
        if isinstance(hotel, dict):
            search = _first(hotel.get("searches"))
            if search:
                return search

        amap = structured_context.get("amap")
        if not isinstance(amap, dict):
            return {}
        stays = amap.get("stays")
        fallback = _first(stays)
        if not fallback:
            return {}
        fallback["price_status"] = "reference"
        return fallback

    @classmethod
    def _extract_map_preview(cls, structured_context: dict[str, Any]) -> dict[str, Any]:
        amap = structured_context.get("amap")
        if not isinstance(amap, dict):
            return {}
        preview = amap.get("map_preview")
        return preview if isinstance(preview, dict) else {}

    @classmethod
    def _extract_assistant_section(cls, structured_context: dict[str, Any], key: str) -> dict[str, Any]:
        assistant = structured_context.get("assistant_plan")
        if not isinstance(assistant, dict):
            return {}
        section = assistant.get(key)
        return section if isinstance(section, dict) else {}

    @classmethod
    def _extract_booking_notices(cls, arrival: dict[str, Any], stay: dict[str, Any]) -> list[dict[str, Any]]:
        notices: list[dict[str, Any]] = []
        if isinstance(arrival.get("official_notice"), dict):
            notices.append(dict(arrival["official_notice"]))
        if stay.get("notes"):
            notices.append({"notice": "酒店价格与房态请以美团、携程、飞猪等第三方平台实际下单页为准。"})
        return notices

    @classmethod
    def _extract_food_summary(cls, trip) -> dict[str, Any]:
        items: list[str] = []
        for day in getattr(trip, "itinerary_days", []) or []:
            for item in getattr(day, "items", []) or []:
                if not isinstance(item, dict) or item.get("type") != "food_recommendations":
                    continue
                for candidate in item.get("items") or []:
                    if isinstance(candidate, dict):
                        name = _strip(candidate.get("name"))
                        if name:
                            items.append(name)
        deduped = list(dict.fromkeys(items))
        return {
            "summary": "推荐围绕每日动线就近安排用餐。" if deduped else "",
            "items": deduped[:6],
        }

    @classmethod
    def _build_daily_itinerary(
        cls,
        trip,
        *,
        arrival: dict[str, Any],
        stay: dict[str, Any],
        structured_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        arrival_day = cls._build_arrival_day(
            trip=trip,
            arrival=arrival,
            stay=stay,
            structured_context=structured_context,
        )
        if arrival_day:
            results.append(arrival_day)
        for day in getattr(trip, "itinerary_days", []) or []:
            items = [item for item in (getattr(day, "items", None) or []) if isinstance(item, dict)]
            periods: list[dict[str, Any]] = []
            for period_key in ("morning", "afternoon", "evening"):
                blocks = cls._build_period_blocks(items, period_key)
                if blocks:
                    periods.append(
                        {
                            "key": period_key,
                            "label": cls.PERIOD_LABELS[period_key],
                            "blocks": blocks,
                        }
                    )
            results.append(
                {
                    "day_no": getattr(day, "day_no", None),
                    "day_type": "itinerary",
                    "title": getattr(day, "title", None),
                    "city_name": getattr(day, "city_name", None),
                    "summary": getattr(day, "summary", None),
                    "weather": None,
                    "periods": periods,
                }
            )
        return results

    @classmethod
    def _build_arrival_day(
        cls,
        *,
        trip,
        arrival: dict[str, Any],
        stay: dict[str, Any],
        structured_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not arrival:
            return None

        top_candidate = _first(arrival.get("candidates"))
        train_label = top_candidate.get("train_no") if isinstance(top_candidate, dict) else None
        station_text = cls._format_arrival_station_text(top_candidate)
        time_text = cls._format_arrival_time_text(top_candidate)
        has_real_ticket = cls._has_real_arrival_ticket(arrival, top_candidate)
        arrival_note_parts = [
            _strip(arrival.get("summary")),
            "暂未获取到真实车次，请以铁路12306官网/App为准。"
            if not has_real_ticket
            else "",
            f"推荐车次：{train_label}" if train_label else "",
            f"站点：{station_text}" if station_text else "",
            f"发到时间：{time_text}" if time_text else "",
            f"票价参考：{arrival.get('price_text')}" if _strip(arrival.get("price_text")) else "",
            f"余票参考：{top_candidate.get('availability_text')}"
            if isinstance(top_candidate, dict) and _strip(top_candidate.get("availability_text"))
            else "",
            f"12306提醒：{arrival.get('official_notice', {}).get('notice')}" if isinstance(arrival.get("official_notice"), dict) else "",
        ]

        summary = _strip(arrival.get("summary"))
        if not summary:
            destination = _strip(arrival.get("destination_city")) or "目的地"
            origin = _strip(arrival.get("origin_city")) or "出发地"
            if has_real_ticket and train_label:
                summary = f"从 {origin} 前往 {destination}，推荐乘坐 {train_label} 抵达后衔接入住或首个景点。"
            else:
                summary = f"从 {origin} 前往 {destination}，当前按高铁/动车到达链路预留，暂未获取到真实车次。"
        transfer_block = cls._build_arrival_transfer_block(
            trip=trip,
            arrival=arrival,
            stay=stay,
            structured_context=structured_context,
            top_candidate=top_candidate,
        )
        transfer_summary = _strip(transfer_block.get("summary"))
        if transfer_summary:
            summary = f"{summary} {transfer_summary}".strip()

        blocks = [
            {
                "title": "跨城抵达",
                "transport": cls._format_arrival_transport(arrival, top_candidate),
                "activity": cls._format_arrival_activity(arrival, stay),
                "note": "；".join(part for part in arrival_note_parts if part),
            }
        ]
        if transfer_block:
            blocks.append(
                {
                    "title": transfer_block.get("title") or "到站后衔接",
                    "transport": transfer_block.get("transport"),
                    "activity": transfer_block.get("activity"),
                    "note": transfer_block.get("note"),
                    "badge": transfer_block.get("badge") or "接驳",
                }
            )

        return {
            "day_no": 0,
            "day_type": "arrival",
            "title": "Day 0 到达日",
            "city_name": _strip(arrival.get("destination_city")) or None,
            "summary": summary,
            "weather": None,
            "arrival_leg": {
                "transport": cls._format_arrival_transport(arrival, top_candidate),
                "station_text": station_text,
                "time_text": time_text,
                "train_no": train_label,
            },
            "transfer_to_stay_or_first_stop": transfer_block,
            "official_notice": arrival.get("official_notice") if isinstance(arrival.get("official_notice"), dict) else {},
            "periods": [
                {
                    "key": "morning",
                    "label": cls.PERIOD_LABELS["morning"],
                    "blocks": blocks,
                }
            ],
        }

    @classmethod
    def _build_arrival_transfer_block(
        cls,
        *,
        trip,
        arrival: dict[str, Any],
        stay: dict[str, Any],
        structured_context: dict[str, Any],
        top_candidate: dict[str, Any] | None,
    ) -> dict[str, Any]:
        stay_primary = _first(stay.get("items")) if isinstance(stay, dict) else None
        stay_name = _strip(stay_primary.get("name")) if isinstance(stay_primary, dict) else ""
        first_stop = cls._extract_first_itinerary_target(trip)
        target_name = stay_name or first_stop or (_strip(arrival.get("destination_city")) or "酒店或首个景点")
        route = cls._find_arrival_transfer_route(
            structured_context=structured_context,
            station_name=_strip(top_candidate.get("arrive_station")) if isinstance(top_candidate, dict) else "",
            target_name=target_name,
        )
        if route:
            route_steps = cls._describe_route_steps(route)
            summary = f"到站后优先前往 {target_name}，先完成落脚再开始当天安排。"
            return {
                "title": "到站后去酒店/首景点",
                "badge": "接驳",
                "summary": summary,
                "transport": cls._format_transport_text(route),
                "activity": (
                    f"从 {_strip(route.get('from')) or _strip(top_candidate.get('arrive_station')) or '到达站'} "
                    f"前往 {target_name}，建议先完成入住或放下行李。"
                ),
                "note": route_steps or "已根据现有路线结果整理首段接驳。",
            }

        if stay_name:
            return {
                "title": "到站后去酒店",
                "badge": "接驳",
                "summary": f"到站后先前往 {stay_name} 办理入住，再开始后续行程。",
                "transport": "优先地铁/打车衔接，暂未获取到逐步路线",
                "activity": f"到站后先前往 {stay_name}，完成入住、放行李后再去首个景点。",
                "note": "暂未获取到站后细路线，可优先打车或按高德实时路线前往酒店。",
            }

        if first_stop:
            return {
                "title": "到站后去首个景点",
                "badge": "接驳",
                "summary": f"到站后直接前往 {first_stop} 开始当天行程。",
                "transport": "优先地铁/公交衔接，暂未获取到逐步路线",
                "activity": f"到站后直接前往 {first_stop}，建议先完成简单补给再开始游玩。",
                "note": "暂未获取到站后细路线，可优先打车/地铁前往首个景点。",
            }

        return {
            "title": "到站后衔接",
            "badge": "接驳",
            "summary": "到站后优先衔接酒店或首个景点。",
            "transport": "优先打车或地铁，暂未获取到逐步路线",
            "activity": "到站后先确认落脚点，再按当天节奏开始行程。",
            "note": "暂未获取到站后细路线，可优先打车/地铁前往。",
        }

    @classmethod
    def _find_arrival_transfer_route(
        cls,
        *,
        structured_context: dict[str, Any],
        station_name: str,
        target_name: str,
    ) -> dict[str, Any] | None:
        amap = structured_context.get("amap")
        if not isinstance(amap, dict):
            return None
        routes = amap.get("routes")
        if not isinstance(routes, list):
            return None

        normalized_station = station_name.replace("站", "")
        normalized_target = target_name.replace("站", "")
        best_route = None
        for route in routes:
            if not isinstance(route, dict):
                continue
            route_kind = _strip(route.get("route_kind"))
            if route_kind not in {"point_to_point", "city_to_city"}:
                continue
            origin = _strip(route.get("origin"))
            destination = _strip(route.get("destination"))
            if normalized_station and normalized_station not in origin.replace("站", ""):
                continue
            if normalized_target and normalized_target not in destination.replace("站", ""):
                continue
            best_route = route
            break
        return best_route

    @staticmethod
    def _extract_first_itinerary_target(trip) -> str:
        itinerary_days = getattr(trip, "itinerary_days", []) or []
        for day in itinerary_days:
            for item in getattr(day, "items", []) or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "spot_sequence":
                    spots = [str(name).strip() for name in item.get("spot_sequence") or [] if _strip(name)]
                    if spots:
                        return spots[0]
                if item.get("type") == "transit" and _strip(item.get("to")):
                    return _strip(item.get("to"))
        return ""

    @staticmethod
    def _describe_route_steps(route: dict[str, Any]) -> str:
        steps = route.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return ""
        descriptions: list[str] = []
        for step in steps[:3]:
            if not isinstance(step, dict):
                continue
            instruction = _strip(step.get("instruction"))
            if instruction:
                descriptions.append(instruction)
        return "；".join(descriptions)

    @staticmethod
    def _format_arrival_transport(arrival: dict[str, Any], candidate: dict[str, Any] | None) -> str:
        parts: list[str] = []
        if _strip(arrival.get("recommended_mode")):
            parts.append(_strip(arrival.get("recommended_mode")))
        if candidate:
            if _strip(candidate.get("train_no")):
                parts.append(_strip(candidate.get("train_no")))
            if _strip(candidate.get("depart_time")) or _strip(candidate.get("arrive_time")):
                parts.append(
                    f"{_strip(candidate.get('depart_time')) or '待补充'} -> "
                    f"{_strip(candidate.get('arrive_time')) or '待补充'}"
                )
        if _strip(arrival.get("duration_text")):
            parts.append(f"耗时 {arrival.get('duration_text')}")
        return "｜".join(part for part in parts if part) or "跨城到达方式待补充"

    @staticmethod
    def _format_arrival_station_text(candidate: dict[str, Any] | None) -> str:
        if not isinstance(candidate, dict):
            return ""
        depart_station = _strip(candidate.get("depart_station"))
        arrive_station = _strip(candidate.get("arrive_station"))
        if depart_station or arrive_station:
            return f"{depart_station or '出发站待补充'} -> {arrive_station or '到达站待补充'}"
        return ""

    @staticmethod
    def _format_arrival_time_text(candidate: dict[str, Any] | None) -> str:
        if not isinstance(candidate, dict):
            return ""
        depart_time = _strip(candidate.get("depart_time"))
        arrive_time = _strip(candidate.get("arrive_time"))
        if depart_time or arrive_time:
            return f"{depart_time or '待补充'} -> {arrive_time or '待补充'}"
        return ""

    @staticmethod
    def _has_real_arrival_ticket(arrival: dict[str, Any], candidate: dict[str, Any] | None) -> bool:
        ticket_status = _strip(arrival.get("ticket_status")).lower()
        data_source = _strip(arrival.get("data_source")).lower()
        train_no = _strip(candidate.get("train_no")) if isinstance(candidate, dict) else ""
        if ticket_status == "placeholder":
            return False
        if data_source == "placeholder":
            return False
        return bool(train_no)

    @staticmethod
    def _format_arrival_activity(arrival: dict[str, Any], stay: dict[str, Any]) -> str:
        destination = _strip(arrival.get("destination_city")) or "目的地"
        stay_primary = _first(stay.get("items")) if isinstance(stay, dict) else None
        stay_name = _strip(stay_primary.get("name")) if isinstance(stay_primary, dict) else ""
        if stay_name:
            return f"先抵达 {destination}，再前往 {stay_name} 办理入住并开始当天行程。"
        return f"先抵达 {destination}，到站后衔接酒店入住或首个景点。"

    @classmethod
    def _build_period_blocks(cls, items: list[dict[str, Any]], period_key: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for item in items:
            item_period = item.get("time_period") or "afternoon"
            if item_period != period_key:
                continue
            item_type = item.get("type")
            if item_type == "spot_sequence":
                spots = [str(name).strip() for name in item.get("spot_sequence") or [] if _strip(name)]
                blocks.append(
                    {
                        "title": "景点顺序",
                        "activity": " -> ".join(spots) if spots else "已生成当日景点顺序",
                        "note": _strip(item.get("optimization_note")),
                    }
                )
            elif item_type == "transit":
                blocks.append(
                    {
                        "title": f"{_strip(item.get('from')) or '起点'} -> {_strip(item.get('to')) or '终点'}",
                        "transport": cls._format_transport_text(item),
                        "activity": cls._format_activity_text(item),
                        "note": cls._format_transit_steps(item),
                    }
                )
            elif item_type == "food_recommendations":
                food_items = []
                for food in item.get("items") or []:
                    if isinstance(food, dict):
                        name = _strip(food.get("name"))
                        if name:
                            food_items.append(name)
                blocks.append(
                    {
                        "title": "附近用餐",
                        "food": "、".join(food_items[:3]) if food_items else _strip(item.get("summary")),
                    }
                )
            elif item_type == "stay_recommendations":
                stay_items = item.get("items") or []
                primary = _first(stay_items)
                blocks.append(
                    {
                        "title": "住宿安排",
                        "activity": _strip(primary.get("name")) if isinstance(primary, dict) else _strip(item.get("summary")),
                        "note": "价格来源："
                        + (_strip(primary.get("价格来源")) if isinstance(primary, dict) else "")
                        if isinstance(primary, dict) and _strip(primary.get("价格来源"))
                        else _strip(item.get("summary")),
                    }
                )
            elif item_type in {"budget_summary", "travel_notes", "planning_assumptions"}:
                blocks.append(
                    {
                        "title": item.get("title") or item_type,
                        "note": _strip(item.get("summary")),
                    }
                )
        return blocks

    @staticmethod
    def _format_transport_text(item: dict[str, Any]) -> str:
        parts = [
            _strip(item.get("mode")),
            _strip(item.get("distance_text")),
            _strip(item.get("duration_text")),
            _strip(item.get("ticket_cost_text")),
        ]
        return "｜".join(part for part in parts if part) or "已整理交通方式"

    @staticmethod
    def _format_activity_text(item: dict[str, Any]) -> str:
        route_kind = _strip(item.get("route_kind"))
        if route_kind == "spot_leg":
            return "按景点动线衔接下一站。"
        if route_kind:
            return f"已写入 {route_kind} 交通安排。"
        return ""

    @staticmethod
    def _format_transit_steps(item: dict[str, Any]) -> str:
        steps = item.get("step_details") or []
        descriptions: list[str] = []
        for step in steps[:2]:
            if not isinstance(step, dict):
                continue
            line = _strip(step.get("line"))
            departure = _strip(step.get("departure_stop"))
            arrival = _strip(step.get("arrival_stop"))
            instruction = _strip(step.get("instruction"))
            if line and (departure or arrival):
                descriptions.append(f"{line} {departure} -> {arrival}".strip())
            elif instruction:
                descriptions.append(instruction)
        return "；".join(descriptions)
