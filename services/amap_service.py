"""高德业务服务层。

这一层负责把第三方返回转成项目内更稳定的数据结构，
避免 Web 层直接依赖高德原始字段。
"""

from __future__ import annotations

import re
from typing import Any
from typing import TYPE_CHECKING

from services.errors import ServiceValidationError

if TYPE_CHECKING:
    from services.integrations.amap_client import AmapClient

_LOCATION_PATTERN = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
AMAP_TYPECODE_FOOD = "050000"
AMAP_TYPECODE_STAY = "100000"
_TOOL_TITLE_RE = re.compile(r"^\d+\.\s*\*\*(?P<name>.+?)\*\*[（(](?P<type>.+?)[）)]$")
_POI_TITLE_RE = re.compile(r"^\d+\.\s*(?P<name>.+?)[（(](?P<type>.+?)[）)]$")
_AMOUNT_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
_SPOT_ROUTE_DETAIL_RE = re.compile(
    r"^### 第\s*(?P<segment_no>\d+)\s*段[:：](?P<origin>.+?)\s*->\s*(?P<destination>.+?)\s*$",
    flags=re.MULTILINE,
)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    """把高德返回的字符串/数字/空数组转成 float。"""
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_inline_details(line: str) -> list[str]:
    normalized = line.replace("｜", "|").replace("；", ";")
    return [part.strip() for part in re.split(r"[|;]", normalized) if part.strip()]


class AmapService:
    """高德能力聚合服务。"""

    def __init__(self, client: "AmapClient" | None = None):
        if client is None:
            from services.integrations.amap_client import AmapClient

            client = AmapClient.from_env()
        self.client = client

    @classmethod
    def extract_structured_context(
        cls,
        tool_outputs: list[str] | None,
    ) -> dict[str, Any]:
        """把高德工具文本输出转成可落库的结构化上下文。"""
        if not tool_outputs:
            return {}

        entries: dict[str, list[dict[str, Any]]] = {
            "geocodes": [],
            "pois": [],
            "routes": [],
            "foods": [],
            "stays": [],
        }
        cards: list[dict[str, Any]] = []

        for raw_output in tool_outputs:
            if not isinstance(raw_output, str):
                continue
            text = raw_output.strip()
            if not text:
                continue

            if text.startswith("【高德地理编码】"):
                item = cls._parse_geocode_tool_output(text)
                if item:
                    entries["geocodes"].append(item)
                continue

            if text.startswith("【高德POI搜索】"):
                item = cls._parse_poi_tool_output(text)
                if item:
                    entries["pois"].append(item)
                    cards.append(
                        cls._build_card(
                            card_type="poi_list",
                            title="POI 候选点位",
                            summary=(
                                f"{item.get('keywords') or '关键词'} 在 "
                                f"{item.get('city') or '不限城市'} 命中 "
                                f"{item.get('count') or 0} 个候选点位"
                            ),
                            data=item,
                        )
                    )
                continue

            if text.startswith("## 景点串联路线"):
                item = cls._parse_spot_route_tool_output(text)
                if item:
                    entries["routes"].append(item)
                    cards.append(
                        cls._build_card(
                            card_type="spot_route",
                            title="景点串联路线",
                            summary=(
                                f"{item.get('city') or '当前城市'}"
                                f"按{item.get('mode') or '未知方式'}串联 "
                                f"{len(item.get('spot_sequence') or [])} 个点位，"
                                f"总耗时 {item.get('total_duration_text') or '未知'}，"
                                f"总距离 {item.get('total_distance_text') or '未知'}"
                            ),
                            data=item,
                        )
                    )
                continue

            if text.startswith("## 城市路线规划"):
                item = cls._parse_route_tool_output(text, route_kind="city_to_city")
                if item:
                    entries["routes"].append(item)
                    cards.append(
                        cls._build_card(
                            card_type="route",
                            title="城市路线规划",
                            summary=(
                                f"{item.get('origin') or '出发地'} -> "
                                f"{item.get('destination') or '目的地'}，"
                                f"{item.get('mode') or '未知方式'}，"
                                f"{item.get('duration_text') or '未知'} / "
                                f"{item.get('distance_text') or '未知'}"
                            ),
                            data=item,
                        )
                    )
                continue

            if text.startswith("## 路线规划"):
                item = cls._parse_route_tool_output(text, route_kind="point_to_point")
                if item:
                    entries["routes"].append(item)
                    cards.append(
                        cls._build_card(
                            card_type="route",
                            title="路线规划",
                            summary=(
                                f"{item.get('origin') or '起点'} -> "
                                f"{item.get('destination') or '终点'}，"
                                f"{item.get('mode') or '未知方式'}，"
                                f"{item.get('duration_text') or '未知'} / "
                                f"{item.get('distance_text') or '未知'}"
                            ),
                            data=item,
                        )
                    )
                continue

            if text.startswith("## 周边美食推荐"):
                item = cls._parse_food_tool_output(text)
                if item:
                    entries["foods"].append(item)
                    cards.append(
                        cls._build_card(
                            card_type="food_recommendations",
                            title="周边美食推荐",
                            summary=(
                                f"{item.get('center') or '中心点'}附近整理出 "
                                f"{len(item.get('items') or [])} 个美食推荐"
                            ),
                            data=item,
                        )
                    )
                continue

            if text.startswith("## 住宿推荐（酒店/民宿）"):
                item = cls._parse_stay_tool_output(text)
                if item:
                    entries["stays"].append(item)
                    cards.append(
                        cls._build_card(
                            card_type="stay_recommendations",
                            title="住宿推荐",
                            summary=(
                                f"{item.get('center') or '中心点'}附近整理出 "
                                f"{len(item.get('items') or [])} 个住宿候选"
                            ),
                            data=item,
                        )
                    )
                continue

        if not cards and not any(entries.values()):
            return {}

        return {
            "provider": "amap",
            "version": 1,
            "cards": cards,
            "geocodes": entries["geocodes"],
            "pois": entries["pois"],
            "routes": entries["routes"],
            "foods": entries["foods"],
            "stays": entries["stays"],
        }

    @staticmethod
    def _build_card(
        *,
        card_type: str,
        title: str,
        summary: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "provider": "amap",
            "type": card_type,
            "title": title,
            "summary": summary,
            "data": data,
        }

    @staticmethod
    def _parse_labeled_lines(text: str) -> dict[str, str]:
        data: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("|"):
                continue
            if line.startswith("- "):
                line = line[2:].strip()
            match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", line)
            if not match:
                continue
            data[match.group("label").strip()] = match.group("value").strip()
        return data

    @staticmethod
    def _parse_number_from_text(value: str | None) -> float | None:
        if not value:
            return None
        match = _AMOUNT_RE.search(value)
        if not match:
            return None
        return _to_float(match.group(1))

    @staticmethod
    def _extract_section_lines(text: str, heading: str) -> list[str]:
        lines = text.splitlines()
        collecting = False
        collected: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            if stripped == heading:
                collecting = True
                continue
            if collecting and stripped.startswith("### "):
                break
            if collecting:
                collected.append(raw_line)
        return collected

    @classmethod
    def _parse_structured_step_lines(cls, lines: list[str]) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        current_step: dict[str, Any] | None = None

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            step_match = re.match(r"^\d+\.\s*(.+)$", stripped)
            if step_match:
                current_step = {"instruction": step_match.group(1).strip()}
                steps.append(current_step)
                continue

            if current_step is None:
                continue

            detail_line = stripped[2:].strip() if stripped.startswith("- ") else stripped
            match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", detail_line)
            if not match:
                continue
            label = match.group("label").strip()
            value = match.group("value").strip()

            if label == "类型":
                current_step["type"] = value
            elif label == "线路":
                current_step["line"] = value
            elif label == "上车站":
                current_step["departure_stop"] = value
            elif label == "下车站":
                current_step["arrival_stop"] = value
            elif label == "站数":
                current_step["via_num"] = _to_int(value)
            elif label == "距离":
                current_step["distance_text"] = value
            elif label in {"预计耗时", "耗时"}:
                current_step["duration_text"] = value
            elif label == "票价参考":
                current_step["ticket_cost_text"] = value
            elif label == "到达点":
                current_step["destination_name"] = value
            elif label == "入口":
                current_step["entrance"] = value
            elif label == "出口":
                current_step["exit"] = value

        for step in steps:
            raw_type = (step.get("type") or "").strip()
            if raw_type in {"步行", "地铁", "公交", "铁路"}:
                continue
            instruction = step.get("instruction") or ""
            if "地铁" in instruction:
                step["type"] = "地铁"
            elif "公交" in instruction:
                step["type"] = "公交"
            elif "铁路" in instruction or "火车" in instruction:
                step["type"] = "铁路"
            else:
                step["type"] = "步行"
        return steps

    @staticmethod
    def _normalize_transit_step_type(raw_type: str | None) -> str:
        text = (raw_type or "").strip().lower()
        if text in {"walk", "walking", "步行"}:
            return "walk"
        if text in {"metro", "subway", "地铁", "轨道"}:
            return "metro"
        if text in {"bus", "公交"}:
            return "bus"
        if text in {"railway", "train", "铁路"}:
            return "railway"
        return text or "other"

    @staticmethod
    def _format_transit_cost(value: Any) -> str | None:
        amount = _to_float(value)
        if amount is None:
            text = str(value or "").strip()
            return text or None
        if amount.is_integer():
            return f"{int(amount)} 元"
        return f"{amount:.1f} 元"

    @staticmethod
    def _clean_line_name(name: str | None) -> str | None:
        text = (name or "").strip()
        if not text:
            return None
        return re.sub(r"\([^)]*\)$", "", text).strip()

    @classmethod
    def _normalize_walk_instruction(
        cls,
        walking: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        walking = walking or {}
        steps = walking.get("steps") or []
        instructions = [
            str(step.get("instruction") or "").strip()
            for step in steps
            if isinstance(step, dict) and str(step.get("instruction") or "").strip()
        ]
        instruction = "；".join(instructions) if instructions else None
        destination = None
        if steps:
            last_step = steps[-1] if isinstance(steps[-1], dict) else {}
            destination = str(last_step.get("assistant_action") or "").strip() or None

        if instruction:
            return instruction, destination

        distance_value = _to_int(walking.get("distance"), default=-1)
        distance_text = f"{distance_value} 米" if distance_value >= 0 else "若干距离"
        if destination:
            return f"步行 {distance_text} 到{destination}", destination
        return f"步行 {distance_text}", destination

    @classmethod
    def _normalize_walking_step(
        cls,
        walking: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        walking = walking or {}
        distance_value = _to_int(walking.get("distance"), default=-1)
        duration_value = _to_int(walking.get("duration"), default=-1)
        instruction, destination = cls._normalize_walk_instruction(walking)

        if distance_value <= 0 and not instruction:
            return None

        step: dict[str, Any] = {
            "type": "walk",
            "instruction": instruction or "步行前往下一段交通",
            "distance": walking.get("distance"),
            "duration": walking.get("duration"),
            "distance_value": distance_value if distance_value >= 0 else None,
            "duration_value": duration_value if duration_value >= 0 else None,
            "destination_name": destination,
        }
        if step["distance_value"] is not None:
            step["distance_text"] = f"{step['distance_value']} 米"
        return step

    @classmethod
    def _normalize_busline_step(
        cls,
        busline: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        busline = busline or {}
        raw_name = str(busline.get("name") or "").strip()
        line_name = cls._clean_line_name(raw_name) or raw_name
        departure_stop = (busline.get("departure_stop") or {}).get("name")
        arrival_stop = (busline.get("arrival_stop") or {}).get("name")
        via_num = _to_int(busline.get("via_num"), default=-1)
        distance_value = _to_int(busline.get("distance"), default=-1)
        duration_value = _to_int(busline.get("duration"), default=-1)
        raw_type = str(busline.get("type") or "")
        step_type = (
            "metro"
            if "地铁" in line_name or "地铁" in raw_type or "轨道" in raw_type
            else "bus"
        )

        if not line_name and not departure_stop and not arrival_stop:
            return None

        line_label = line_name or "公共交通"
        instruction = f"乘坐 {line_label}"
        if departure_stop and arrival_stop:
            instruction += f"，从 {departure_stop} 到 {arrival_stop}"
        elif departure_stop:
            instruction += f"，在 {departure_stop} 上车"
        if via_num >= 0:
            instruction += f"，经过 {via_num} 站"

        return {
            "type": step_type,
            "line": line_label,
            "instruction": instruction,
            "departure_stop": departure_stop,
            "arrival_stop": arrival_stop,
            "via_num": via_num if via_num >= 0 else None,
            "distance": busline.get("distance"),
            "duration": busline.get("duration"),
            "distance_value": distance_value if distance_value >= 0 else None,
            "duration_value": duration_value if duration_value >= 0 else None,
            "start_time": busline.get("start_time"),
            "end_time": busline.get("end_time"),
        }

    @classmethod
    def _normalize_railway_step(
        cls,
        railway: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        railway = railway or {}
        if not railway:
            return None
        trip_name = str(
            railway.get("trip") or railway.get("name") or railway.get("id") or ""
        ).strip()
        departure_stop = (railway.get("departure_stop") or {}).get("name")
        arrival_stop = (railway.get("arrival_stop") or {}).get("name")
        distance_value = _to_int(railway.get("distance"), default=-1)
        duration_value = _to_int(railway.get("time"), default=-1)

        if not departure_stop and not arrival_stop and not trip_name:
            return None

        instruction = f"乘坐 {trip_name or '铁路'}"
        if departure_stop and arrival_stop:
            instruction += f"，从 {departure_stop} 到 {arrival_stop}"

        return {
            "type": "railway",
            "line": trip_name or "铁路",
            "instruction": instruction,
            "departure_stop": departure_stop,
            "arrival_stop": arrival_stop,
            "distance": railway.get("distance"),
            "duration": railway.get("time"),
            "distance_value": distance_value if distance_value >= 0 else None,
            "duration_value": duration_value if duration_value >= 0 else None,
        }

    @classmethod
    def _normalize_transit_segments(
        cls,
        transit: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        transit = transit or {}
        normalized_segments: list[dict[str, Any]] = []
        flat_steps: list[dict[str, Any]] = []

        for index, raw_segment in enumerate(transit.get("segments") or [], start=1):
            segment = raw_segment or {}
            segment_steps: list[dict[str, Any]] = []

            walking_step = cls._normalize_walking_step(segment.get("walking"))
            if walking_step:
                segment_steps.append(walking_step)

            bus = segment.get("bus") or {}
            for raw_busline in bus.get("buslines") or []:
                busline_step = cls._normalize_busline_step(raw_busline)
                if busline_step:
                    entrance = (raw_busline.get("entrance") or {}).get("name") or (
                        segment.get("entrance") or {}
                    ).get("name")
                    exit_name = (raw_busline.get("exit") or {}).get("name") or (
                        segment.get("exit") or {}
                    ).get("name")
                    if entrance:
                        busline_step["entrance"] = entrance
                    if exit_name:
                        busline_step["exit"] = exit_name
                    segment_steps.append(busline_step)

            railway_step = cls._normalize_railway_step(segment.get("railway"))
            if railway_step:
                segment_steps.append(railway_step)

            if not segment_steps:
                continue

            normalized_segments.append({"segment_no": index, "steps": segment_steps})
            flat_steps.extend(segment_steps)

        return normalized_segments, flat_steps

    @classmethod
    def _normalize_transit_option(
        cls,
        transit: dict[str, Any] | None,
    ) -> dict[str, Any]:
        transit = transit or {}
        segments, steps = cls._normalize_transit_segments(transit)
        distance_value = _to_int(transit.get("distance"), default=-1)
        duration_value = _to_int(transit.get("duration"), default=-1)
        walking_distance_value = _to_int(transit.get("walking_distance"), default=-1)
        cost_value = _to_float(transit.get("cost"))

        return {
            "distance": transit.get("distance"),
            "duration": transit.get("duration"),
            "walking_distance": transit.get("walking_distance"),
            "cost": transit.get("cost"),
            "distance_value": distance_value if distance_value >= 0 else None,
            "duration_value": duration_value if duration_value >= 0 else None,
            "walking_distance_value": (
                walking_distance_value if walking_distance_value >= 0 else None
            ),
            "cost_value": cost_value,
            "cost_text": cls._format_transit_cost(transit.get("cost")),
            "nightflag": transit.get("nightflag"),
            "missed": transit.get("missed"),
            "segments": segments,
            "steps": steps,
            "transfer_count": max(
                len(
                    [
                        step
                        for step in steps
                        if step.get("type") in {"bus", "metro", "railway"}
                    ]
                )
                - 1,
                0,
            ),
            "raw": transit,
        }

    @classmethod
    def _parse_geocode_tool_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        if not data.get("地址") and not data.get("坐标"):
            return None
        return {
            "address": data.get("地址"),
            "location": data.get("坐标"),
            "administrative_area": data.get("行政区"),
            "match_count": _to_int(data.get("匹配数")),
        }

    @classmethod
    def _parse_poi_tool_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        items: list[dict[str, Any]] = []
        current_item: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            title_match = _POI_TITLE_RE.match(line)
            if title_match:
                current_item = {
                    "name": title_match.group("name").strip(),
                    "type": title_match.group("type").strip(),
                }
                items.append(current_item)
                continue
            if current_item is None or not line.startswith("地址："):
                continue
            for part in _split_inline_details(line):
                match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", part)
                if not match:
                    continue
                label = match.group("label").strip()
                value = match.group("value").strip()
                if label == "地址":
                    current_item["address"] = value
                elif label == "坐标":
                    current_item["location"] = value

        if not data.get("关键词") and not items:
            return None
        return {
            "keywords": data.get("关键词"),
            "city": data.get("城市"),
            "count": _to_int(data.get("命中总数")),
            "items": items,
        }

    @classmethod
    def _parse_route_tool_output(
        cls,
        text: str,
        *,
        route_kind: str,
    ) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        origin = data.get("起点") or data.get("出发城市")
        destination = data.get("终点") or data.get("目的城市")
        if not origin and not destination:
            return None
        item = {
            "route_kind": route_kind,
            "origin": origin,
            "destination": destination,
            "mode": data.get("出行方式"),
            "city": data.get("城市"),
            "distance_text": data.get("距离") or data.get("跨城驾车距离"),
            "duration_text": data.get("预计耗时") or data.get("跨城驾车耗时"),
            "taxi_cost_text": data.get("打车参考价"),
            "ticket_cost_text": data.get("票价参考"),
            "walking_distance_text": data.get("总步行距离"),
            "note": data.get("说明"),
        }
        step_lines = cls._extract_section_lines(text, "### 逐步换乘")
        if step_lines:
            item["steps"] = cls._parse_structured_step_lines(step_lines)
        if item["distance_text"]:
            item["distance_value"] = cls._parse_number_from_text(item["distance_text"])
        if item["duration_text"]:
            item["duration_value"] = cls._parse_number_from_text(item["duration_text"])
        return item

    @classmethod
    def _parse_food_tool_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        items: list[dict[str, Any]] = []
        current_item: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            title_match = _TOOL_TITLE_RE.match(line)
            if title_match:
                current_item = {
                    "name": title_match.group("name").strip(),
                    "type": title_match.group("type").strip(),
                }
                items.append(current_item)
                continue
            if current_item is None or not line.startswith("距离："):
                continue
            for part in _split_inline_details(line):
                match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", part)
                if not match:
                    continue
                label = match.group("label").strip()
                value = match.group("value").strip()
                if label == "距离":
                    current_item["distance_text"] = value
                elif label == "地址":
                    current_item["address"] = value

        if not data.get("中心点") and not items:
            return None
        return {
            "center": data.get("中心点"),
            "radius_text": data.get("搜索半径"),
            "count": _to_int(data.get("命中总数")),
            "items": items,
        }

    @classmethod
    def _parse_stay_tool_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        items: list[dict[str, Any]] = []
        current_item: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            title_match = _TOOL_TITLE_RE.match(line)
            if title_match:
                current_item = {
                    "name": title_match.group("name").strip(),
                    "type": title_match.group("type").strip(),
                }
                items.append(current_item)
                continue
            if current_item is None:
                continue
            if line.startswith("距离："):
                for part in _split_inline_details(line):
                    match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", part)
                    if not match:
                        continue
                    label = match.group("label").strip()
                    value = match.group("value").strip()
                    if label == "距离":
                        current_item["distance_text"] = value
                    elif label == "评分":
                        current_item["rating_text"] = value
                    elif label == "人均":
                        current_item["budget_text"] = value
                continue
            if line.startswith("价格来源："):
                current_item["price_source"] = line.split("：", 1)[1].strip()
                continue
            if line.startswith("地址："):
                for part in _split_inline_details(line):
                    match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", part)
                    if not match:
                        continue
                    label = match.group("label").strip()
                    value = match.group("value").strip()
                    if label == "地址":
                        current_item["address"] = value
                    elif label == "电话":
                        current_item["tel"] = value
                continue

        filtered_count = None
        before_filter_count = None
        filtered_text = data.get("筛选后数量")
        if filtered_text and "/" in filtered_text:
            current, total = filtered_text.split("/", 1)
            filtered_count = _to_int(current)
            before_filter_count = _to_int(total)

        if not data.get("中心点") and not items:
            return None
        return {
            "center": data.get("中心点"),
            "radius_text": data.get("搜索半径"),
            "filtered_count": filtered_count,
            "before_filter_count": before_filter_count,
            "filter_summary": data.get("筛选条件"),
            "items": items,
        }

    @classmethod
    def _parse_spot_route_tool_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        legs: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 5 or cells[0] in {"段落", "---"}:
                continue
            legs.append(
                {
                    "segment_no": _to_int(cells[0]),
                    "origin": cells[1],
                    "destination": cells[2],
                    "distance_text": cells[3],
                    "duration_text": cells[4],
                }
            )

        spot_sequence = [
            part.strip()
            for part in (data.get("景点顺序") or "").split("->")
            if part.strip()
        ]
        detail_matches = list(_SPOT_ROUTE_DETAIL_RE.finditer(text))
        for index, match in enumerate(detail_matches):
            block_start = match.end()
            block_end = (
                detail_matches[index + 1].start()
                if index + 1 < len(detail_matches)
                else len(text)
            )
            block = text[block_start:block_end]
            block_data = cls._parse_labeled_lines(block)
            step_lines = [
                raw_line
                for raw_line in block.splitlines()
                if re.match(r"^\s*\d+\.\s+", raw_line) or raw_line.strip().startswith("- ")
            ]
            steps = cls._parse_structured_step_lines(step_lines)

            leg = next(
                (
                    item
                    for item in legs
                    if item.get("segment_no") == _to_int(match.group("segment_no"))
                ),
                None,
            )
            if leg is None:
                leg = {
                    "segment_no": _to_int(match.group("segment_no")),
                    "origin": match.group("origin").strip(),
                    "destination": match.group("destination").strip(),
                }
                legs.append(leg)

            leg["mode"] = block_data.get("出行方式") or data.get("出行方式")
            leg["distance_text"] = block_data.get("距离") or leg.get("distance_text")
            leg["duration_text"] = block_data.get("耗时") or leg.get("duration_text")
            leg["ticket_cost_text"] = block_data.get("票价参考")
            leg["walking_distance_text"] = block_data.get("总步行距离")
            if steps:
                leg["steps"] = steps

        if not data.get("城市") and not legs:
            return None
        return {
            "route_kind": "spot_sequence",
            "city": data.get("城市"),
            "mode": data.get("出行方式"),
            "spot_sequence": spot_sequence,
            "original_spot_sequence": [
                part.strip()
                for part in (data.get("原始顺序") or "").split("->")
                if part.strip()
            ],
            "optimization_note": data.get("自动顺序优化"),
            "legs": sorted(legs, key=lambda item: item.get("segment_no") or 0),
            "total_distance_text": data.get("总距离"),
            "total_duration_text": data.get("总耗时"),
            "note": data.get("说明"),
        }

    @staticmethod
    def _ensure_text(value: str, *, field_name: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ServiceValidationError(f"{field_name} 不能为空。")
        return text

    @staticmethod
    def _ensure_location(value: str, *, field_name: str = "location") -> str:
        location = (value or "").strip()
        if not location:
            raise ServiceValidationError(f"{field_name} 不能为空，应为 lng,lat。")
        if not _LOCATION_PATTERN.match(location):
            raise ServiceValidationError(
                f"{field_name} 格式不正确，应为 lng,lat，例如 116.481488,39.990464。"
            )
        return location

    @staticmethod
    def _resolve_item_price(item: dict[str, Any]) -> tuple[float | None, str | None]:
        lowest_price = _to_float(item.get("lowest_price"))
        if lowest_price is not None:
            return lowest_price, "lowest_price"
        cost = _to_float(item.get("cost"))
        if cost is not None:
            return cost, "cost"
        return None, None

    @classmethod
    def _serialize_poi_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        """统一 POI 输出结构，便于前端和工具层复用。"""
        biz_ext = item.get("biz_ext") or {}
        if not isinstance(biz_ext, dict):
            biz_ext = {}
        rating = _to_float(biz_ext.get("rating"))
        cost = _to_float(biz_ext.get("cost"))
        lowest_price = _to_float(biz_ext.get("lowest_price"))
        distance = _to_int(item.get("distance"), default=-1)
        resolved_price, price_source = cls._resolve_item_price(
            {"lowest_price": lowest_price, "cost": cost}
        )
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "typecode": item.get("typecode"),
            "address": item.get("address"),
            "location": item.get("location"),
            "distance": item.get("distance"),
            "distance_m": (distance if distance >= 0 else None),
            "tel": item.get("tel"),
            "business_area": item.get("business_area"),
            "rating": rating,
            "cost": cost,
            "lowest_price": lowest_price,
            "resolved_price": resolved_price,
            "price_source": price_source,
            "biz_ext": biz_ext,
        }

    def geocode(self, *, address: str, city: str | None = None) -> dict[str, Any]:
        """地址转经纬度。"""
        address = self._ensure_text(address, field_name="address")
        payload = self.client.geocode(address=address, city=(city or "").strip() or None)
        geocodes = payload.get("geocodes") or []
        items = [
            {
                "formatted_address": item.get("formatted_address"),
                "province": item.get("province"),
                "city": item.get("city"),
                "district": item.get("district"),
                "adcode": item.get("adcode"),
                "location": item.get("location"),
                "level": item.get("level"),
            }
            for item in geocodes
        ]
        return {
            "query": {
                "address": address,
                "city": (city or "").strip() or None,
            },
            "count": _to_int(payload.get("count")),
            "primary": items[0] if items else None,
            "items": items,
            "raw": payload,
        }

    def reverse_geocode(
        self,
        *,
        location: str,
        radius: int = 1000,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """经纬度转地址。"""
        location = self._ensure_location(location)
        if radius <= 0:
            raise ServiceValidationError("radius 必须大于 0。")
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.reverse_geocode(
            location=location,
            radius=radius,
            extensions=extensions,
        )
        regeo = payload.get("regeocode") or {}
        address_component = regeo.get("addressComponent") or {}
        return {
            "query": {
                "location": location,
                "radius": radius,
                "extensions": extensions,
            },
            "formatted_address": regeo.get("formatted_address"),
            "province": address_component.get("province"),
            "city": address_component.get("city"),
            "district": address_component.get("district"),
            "township": address_component.get("township"),
            "adcode": address_component.get("adcode"),
            "pois": regeo.get("pois") or [],
            "roads": regeo.get("roads") or [],
            "raw": payload,
        }

    def search_poi(
        self,
        *,
        keywords: str,
        city: str | None = None,
        city_limit: bool = True,
        types: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """POI 搜索。"""
        keywords = self._ensure_text(keywords, field_name="keywords")
        if page <= 0:
            raise ServiceValidationError("page 必须大于 0。")
        if page_size <= 0 or page_size > 25:
            raise ServiceValidationError("page_size 必须在 1-25 之间。")

        payload = self.client.search_poi(
            keywords=keywords,
            city=(city or "").strip() or None,
            city_limit=city_limit,
            types=(types or "").strip() or None,
            page=page,
            offset=page_size,
        )
        pois = payload.get("pois") or []
        items = [self._serialize_poi_item(item) for item in pois]
        return {
            "query": {
                "keywords": keywords,
                "city": (city or "").strip() or None,
                "city_limit": city_limit,
                "types": (types or "").strip() or None,
                "page": page,
                "page_size": page_size,
            },
            "count": _to_int(payload.get("count")),
            "items": items,
            "raw": payload,
        }

    def search_nearby(
        self,
        *,
        location: str,
        keywords: str | None = None,
        types: str | None = None,
        radius: int = 3000,
        page: int = 1,
        page_size: int = 10,
        sortrule: str = "distance",
    ) -> dict[str, Any]:
        """周边搜索。"""
        location = self._ensure_location(location)
        if radius <= 0 or radius > 50000:
            raise ServiceValidationError("radius 必须在 1-50000 米之间。")
        if page <= 0:
            raise ServiceValidationError("page 必须大于 0。")
        if page_size <= 0 or page_size > 25:
            raise ServiceValidationError("page_size 必须在 1-25 之间。")
        if sortrule not in {"distance", "weight"}:
            raise ServiceValidationError("sortrule 仅支持 distance 或 weight。")

        payload = self.client.search_around(
            location=location,
            keywords=(keywords or "").strip() or None,
            types=(types or "").strip() or None,
            radius=radius,
            sortrule=sortrule,
            page=page,
            offset=page_size,
        )
        pois = payload.get("pois") or []
        items = [self._serialize_poi_item(item) for item in pois]
        return {
            "query": {
                "location": location,
                "keywords": (keywords or "").strip() or None,
                "types": (types or "").strip() or None,
                "radius": radius,
                "page": page,
                "page_size": page_size,
                "sortrule": sortrule,
            },
            "count": _to_int(payload.get("count")),
            "items": items,
            "raw": payload,
        }

    def search_nearby_food(
        self,
        *,
        location: str,
        radius: int = 3000,
        page: int = 1,
        page_size: int = 10,
        sortrule: str = "distance",
    ) -> dict[str, Any]:
        """周边美食搜索。"""
        return self.search_nearby(
            location=location,
            types=AMAP_TYPECODE_FOOD,
            radius=radius,
            page=page,
            page_size=page_size,
            sortrule=sortrule,
        )

    def search_nearby_stay(
        self,
        *,
        location: str,
        keyword: str | None = None,
        radius: int = 5000,
        page: int = 1,
        page_size: int = 10,
        sortrule: str = "distance",
    ) -> dict[str, Any]:
        """周边住宿搜索（酒店/民宿）。"""
        return self.search_nearby(
            location=location,
            keywords=keyword,
            types=AMAP_TYPECODE_STAY,
            radius=radius,
            page=page,
            page_size=page_size,
            sortrule=sortrule,
        )

    def search_stays_with_filters(
        self,
        *,
        location: str,
        radius: int = 5000,
        limit: int = 10,
        min_rating: float | None = None,
        max_budget: float | None = None,
        max_distance_m: int | None = None,
        include_unknown_rating: bool = True,
        include_unknown_budget: bool = True,
    ) -> dict[str, Any]:
        """住宿搜索并按预算、评分、距离筛选。"""
        location = self._ensure_location(location)
        if radius <= 0 or radius > 50000:
            raise ServiceValidationError("radius 必须在 1-50000 米之间。")
        if limit <= 0 or limit > 25:
            raise ServiceValidationError("limit 必须在 1-25 之间。")
        if min_rating is not None and not (0 <= min_rating <= 5):
            raise ServiceValidationError("min_rating 必须在 0-5 之间。")
        if max_budget is not None and max_budget <= 0:
            raise ServiceValidationError("max_budget 必须大于 0。")
        if max_distance_m is not None and max_distance_m <= 0:
            raise ServiceValidationError("max_distance_m 必须大于 0。")

        hotel_result = self.search_nearby_stay(
            location=location,
            keyword="酒店",
            radius=radius,
            page=1,
            page_size=limit,
        )
        homestay_result = self.search_nearby_stay(
            location=location,
            keyword="民宿",
            radius=radius,
            page=1,
            page_size=limit,
        )
        merged = self._merge_unique_poi_items(
            hotel_result.get("items") or [],
            homestay_result.get("items") or [],
        )
        before_filter_count = len(merged)
        filtered = [
            item
            for item in merged
            if self._match_stay_filters(
                item=item,
                min_rating=min_rating,
                max_budget=max_budget,
                max_distance_m=max_distance_m,
                include_unknown_rating=include_unknown_rating,
                include_unknown_budget=include_unknown_budget,
            )
        ]
        filtered.sort(
            key=lambda x: (
                x.get("distance_m") if x.get("distance_m") is not None else 10**9,
                -(x.get("rating") if x.get("rating") is not None else -1),
                (
                    self._resolve_item_price(x)[0]
                    if self._resolve_item_price(x)[0] is not None
                    else 10**9
                ),
            )
        )
        return {
            "query": {
                "location": location,
                "radius": radius,
                "limit": limit,
                "min_rating": min_rating,
                "max_budget": max_budget,
                "max_distance_m": max_distance_m,
                "include_unknown_rating": include_unknown_rating,
                "include_unknown_budget": include_unknown_budget,
            },
            "before_filter_count": before_filter_count,
            "count": len(filtered),
            "items": filtered[:limit],
        }

    @staticmethod
    def _merge_unique_poi_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按 id + location 去重合并。"""
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
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
        return merged

    @classmethod
    def _match_stay_filters(
        cls,
        *,
        item: dict[str, Any],
        min_rating: float | None,
        max_budget: float | None,
        max_distance_m: int | None,
        include_unknown_rating: bool,
        include_unknown_budget: bool,
    ) -> bool:
        """判断住宿是否命中过滤条件。"""
        distance_m = item.get("distance_m")
        rating = item.get("rating")
        budget, _ = cls._resolve_item_price(item)

        if max_distance_m is not None:
            if distance_m is None:
                return False
            if distance_m > max_distance_m:
                return False

        if min_rating is not None:
            if rating is None and not include_unknown_rating:
                return False
            if rating is not None and rating < min_rating:
                return False

        if max_budget is not None:
            if budget is None and not include_unknown_budget:
                return False
            if budget is not None and budget > max_budget:
                return False

        return True

    def route_driving(
        self,
        *,
        origin: str,
        destination: str,
        strategy: int = 0,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """驾车路线。"""
        origin = self._ensure_location(origin, field_name="origin")
        destination = self._ensure_location(destination, field_name="destination")
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.route_driving(
            origin=origin,
            destination=destination,
            strategy=strategy,
            extensions=extensions,
        )
        route = payload.get("route") or {}
        paths = route.get("paths") or []
        return {
            "query": {
                "origin": origin,
                "destination": destination,
                "strategy": strategy,
                "extensions": extensions,
            },
            "origin": route.get("origin"),
            "destination": route.get("destination"),
            "taxi_cost": route.get("taxi_cost"),
            "path_count": len(paths),
            "paths": paths,
            "primary_path": paths[0] if paths else None,
            "raw": payload,
        }

    def route_walking(self, *, origin: str, destination: str) -> dict[str, Any]:
        """步行路线。"""
        origin = self._ensure_location(origin, field_name="origin")
        destination = self._ensure_location(destination, field_name="destination")

        payload = self.client.route_walking(origin=origin, destination=destination)
        route = payload.get("route") or {}
        paths = route.get("paths") or []
        return {
            "query": {
                "origin": origin,
                "destination": destination,
            },
            "path_count": len(paths),
            "paths": paths,
            "primary_path": paths[0] if paths else None,
            "raw": payload,
        }

    def route_transit(
        self,
        *,
        origin: str,
        destination: str,
        city: str,
        cityd: str | None = None,
        strategy: int = 0,
        nightflag: int = 0,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """公交/地铁路线。"""
        origin = self._ensure_location(origin, field_name="origin")
        destination = self._ensure_location(destination, field_name="destination")
        city = self._ensure_text(city, field_name="city")
        cityd = (cityd or "").strip() or None
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.route_transit(
            origin=origin,
            destination=destination,
            city=city,
            cityd=cityd,
            strategy=strategy,
            nightflag=nightflag,
            extensions=extensions,
        )
        route = payload.get("route") or {}
        transits = [self._normalize_transit_option(item) for item in route.get("transits") or []]
        return {
            "query": {
                "origin": origin,
                "destination": destination,
                "city": city,
                "cityd": cityd,
                "strategy": strategy,
                "nightflag": nightflag,
                "extensions": extensions,
            },
            "path_count": len(transits),
            "transits": transits,
            "primary_transit": transits[0] if transits else None,
            "raw": payload,
        }

    def weather(self, *, city: str, extensions: str = "base") -> dict[str, Any]:
        """城市天气。"""
        city = self._ensure_text(city, field_name="city")
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.weather(city=city, extensions=extensions)
        return {
            "query": {
                "city": city,
                "extensions": extensions,
            },
            "lives": payload.get("lives") or [],
            "forecasts": payload.get("forecasts") or [],
            "raw": payload,
        }
