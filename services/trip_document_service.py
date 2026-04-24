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
        budget = cls._extract_assistant_section(context, "budget")
        notes = cls._extract_assistant_section(context, "notes")
        assumptions = cls._extract_assistant_section(context, "assumptions")
        reasons = cls._extract_assistant_section(context, "reasons")
        booking_notices = cls._extract_booking_notices(arrival, stay)
        daily_itinerary = cls._build_daily_itinerary(trip, arrival=arrival, stay=stay)
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

        if daily_itinerary:
            lines.extend(["", "## 每日行程"])
            for day in daily_itinerary:
                lines.extend(["", f"### Day {day.get('day_no')}: {day.get('title') or '当日安排'}"])
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
    def _build_daily_itinerary(cls, trip, *, arrival: dict[str, Any], stay: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
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
            if getattr(day, "day_no", None) == 1:
                periods = cls._inject_arrival_blocks(periods, arrival=arrival, stay=stay)
            results.append(
                {
                    "day_no": getattr(day, "day_no", None),
                    "title": getattr(day, "title", None),
                    "city_name": getattr(day, "city_name", None),
                    "summary": getattr(day, "summary", None),
                    "weather": None,
                    "periods": periods,
                }
            )
        return results

    @classmethod
    def _inject_arrival_blocks(
        cls,
        periods: list[dict[str, Any]],
        *,
        arrival: dict[str, Any],
        stay: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not arrival:
            return periods

        injected_periods = [dict(period) for period in periods]
        morning_period = next(
            (period for period in injected_periods if period.get("key") == "morning"),
            None,
        )
        if morning_period is None:
            morning_period = {"key": "morning", "label": cls.PERIOD_LABELS["morning"], "blocks": []}
            injected_periods.insert(0, morning_period)

        blocks = list(morning_period.get("blocks") or [])
        top_candidate = _first(arrival.get("candidates"))
        train_label = top_candidate.get("train_no") if isinstance(top_candidate, dict) else None
        station_text = None
        if isinstance(top_candidate, dict):
            depart_station = _strip(top_candidate.get("depart_station"))
            arrive_station = _strip(top_candidate.get("arrive_station"))
            if depart_station or arrive_station:
                station_text = f"{depart_station or '出发站待补充'} -> {arrive_station or '到达站待补充'}"
        arrival_note_parts = [
            _strip(arrival.get("summary")),
            f"推荐车次：{train_label}" if train_label else "",
            f"站点：{station_text}" if station_text else "",
            f"票价参考：{arrival.get('price_text')}" if _strip(arrival.get("price_text")) else "",
            f"12306提醒：{arrival.get('official_notice', {}).get('notice')}" if isinstance(arrival.get("official_notice"), dict) else "",
        ]
        blocks.insert(
            0,
            {
                "title": "跨城抵达",
                "transport": cls._format_arrival_transport(arrival, top_candidate),
                "activity": cls._format_arrival_activity(arrival, stay),
                "note": "；".join(part for part in arrival_note_parts if part),
            },
        )
        morning_period["blocks"] = blocks
        return injected_periods

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
