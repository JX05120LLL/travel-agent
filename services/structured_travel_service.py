"""通用旅行结构化服务。

负责把：
1. 工具输出中的跨城到达建议（12306）；
2. 工具输出中的酒店/民宿候选；
3. 助手最终回答里的预算汇总、注意事项、本次假设、推荐理由；

统一抽成可写入 plan_option / trip 的 structured_context。
"""

from __future__ import annotations

import re
from typing import Any

from services.amap_service import AmapService


class StructuredTravelService:
    """聚合地图工具结果与回答级结构化信息。"""

    _HEADING_RE = re.compile(r"^(?P<level>#{2,3})\s*(?P<title>.+?)\s*$")

    @classmethod
    def build_from_message(cls, message) -> dict[str, Any] | None:
        """从消息对象中提取统一 structured_context。"""
        metadata = getattr(message, "message_metadata", None) or {}
        tool_outputs = metadata.get("tool_outputs")
        content = getattr(message, "content", None)

        structured_context = cls.extract_structured_context(
            tool_outputs=tool_outputs if isinstance(tool_outputs, list) else None,
            content=content if isinstance(content, str) else None,
        )
        if not structured_context:
            return None

        message_id = getattr(message, "id", None)
        if message_id is None:
            return structured_context

        enriched: dict[str, Any] = {}
        for key, value in structured_context.items():
            if isinstance(value, dict):
                copied = dict(value)
                copied["source_message_id"] = str(message_id)
                enriched[key] = copied
            else:
                enriched[key] = value
        return enriched

    @classmethod
    def extract_structured_context(
        cls,
        *,
        tool_outputs: list[str] | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """把工具输出与回答正文合并成统一 structured_context。"""
        structured_context: dict[str, Any] = {}

        amap_context = AmapService.extract_structured_context(tool_outputs)
        if amap_context:
            structured_context["amap"] = amap_context

        railway_context = cls._extract_railway_arrival_context(tool_outputs)
        if railway_context:
            structured_context["railway12306"] = railway_context

        hotel_context = cls._extract_hotel_accommodation_context(tool_outputs)
        if hotel_context:
            structured_context["hotel_accommodation"] = hotel_context

        assistant_context = cls._extract_assistant_plan_context(content)
        if assistant_context:
            structured_context["assistant_plan"] = assistant_context

        return structured_context

    @staticmethod
    def _build_card(
        *,
        provider: str,
        card_type: str,
        title: str,
        summary: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "provider": provider,
            "type": card_type,
            "title": title,
            "summary": summary,
            "data": data,
        }

    @classmethod
    def _extract_railway_arrival_context(
        cls,
        tool_outputs: list[str] | None,
    ) -> dict[str, Any] | None:
        if not tool_outputs:
            return None

        arrivals: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        for raw_output in tool_outputs:
            if not isinstance(raw_output, str):
                continue
            text = raw_output.strip()
            if not (
                text.startswith("## 跨城到达建议（12306）")
                or text.startswith("## 跨城到达建议（12306预留）")
            ):
                continue
            item = cls._parse_railway_arrival_output(text)
            if not item:
                continue
            arrivals.append(item)
            cards.append(
                cls._build_card(
                    provider="railway12306",
                    card_type="arrival_recommendation",
                    title="跨城到达建议",
                    summary=item.get("summary")
                    or (
                        f"{item.get('origin_city') or '出发地待补充'} -> "
                        f"{item.get('destination_city') or '目的地待补充'}，"
                        f"{item.get('recommended_mode') or '待补充方式'}"
                    ),
                    data=item,
                )
            )

        if not cards:
            return None

        return {
            "provider": "railway12306",
            "version": 1,
            "cards": cards,
            "arrivals": arrivals,
        }

    @classmethod
    def _parse_railway_arrival_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        candidate_lines = cls._extract_section_lines(text, {"推荐车次"})
        note_lines = cls._extract_section_lines(text, {"补充说明"})
        note_items = cls._normalize_section_items(note_lines)
        if not data and not note_items and not candidate_lines:
            return None

        candidate_items = cls._parse_railway_candidate_items(candidate_lines)
        official_lines = cls._extract_section_lines(text, {"官方购票提醒"})
        official_notice = cls._parse_labeled_section(official_lines)
        return {
            "origin_city": data.get("出发城市"),
            "destination_city": data.get("目的城市"),
            "depart_date": data.get("出发日期"),
            "recommended_mode": data.get("推荐方式"),
            "duration_text": data.get("预计耗时"),
            "price_text": data.get("票价参考"),
            "booking_status": data.get("接入状态"),
            "ticket_status": data.get("票务状态"),
            "data_source": data.get("数据来源"),
            "fetched_at": data.get("数据时效"),
            "degraded_reason": data.get("降级原因"),
            "summary": data.get("方案摘要"),
            "candidates": candidate_items,
            "official_notice": official_notice,
            "notes": note_items,
        }

    @classmethod
    def _extract_hotel_accommodation_context(
        cls,
        tool_outputs: list[str] | None,
    ) -> dict[str, Any] | None:
        if not tool_outputs:
            return None

        hotels: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        for raw_output in tool_outputs:
            if not isinstance(raw_output, str):
                continue
            text = raw_output.strip()
            if not text.startswith("## 酒店民宿推荐（供应商聚合）"):
                continue
            item = cls._parse_hotel_tool_output(text)
            if not item:
                continue
            hotels.append(item)
            cards.append(
                cls._build_card(
                    provider="hotel",
                    card_type="stay_recommendations",
                    title="酒店民宿推荐",
                    summary=item.get("summary") or "已整理住宿候选与价格来源。",
                    data=item,
                )
            )

        if not cards:
            return None

        return {
            "provider": "hotel",
            "version": 1,
            "cards": cards,
            "searches": hotels,
        }

    @classmethod
    def _parse_hotel_tool_output(cls, text: str) -> dict[str, Any] | None:
        data = cls._parse_labeled_lines(text)
        reminder_lines = cls._extract_section_lines(text, {"预订提醒"})
        reminders = cls._normalize_section_items(reminder_lines)
        items: list[dict[str, Any]] = []
        current_item: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            title_match = re.match(r"^\d+\.\s+\*\*(?P<name>.+?)\*\*（(?P<type>.+?)）$", line)
            if title_match:
                current_item = {
                    "name": title_match.group("name").strip(),
                    "type": title_match.group("type").strip(),
                }
                items.append(current_item)
                continue
            if current_item is None or not line.startswith("- "):
                continue
            detail = line[2:].strip()
            match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", detail)
            if not match:
                continue
            label = match.group("label").strip()
            value = match.group("value").strip()
            current_item[label] = value

        if not data and not items:
            return None

        first_item = items[0] if items else {}
        summary = None
        if first_item:
            summary_parts = [
                first_item.get("name"),
                first_item.get("价格"),
                first_item.get("价格来源"),
                first_item.get("片区"),
            ]
            summary = "，".join(str(part) for part in summary_parts if str(part or "").strip())

        return {
            "destination": data.get("目的地"),
            "center": data.get("中心点"),
            "radius_text": data.get("搜索半径"),
            "provider": data.get("推荐来源"),
            "price_status": data.get("价格状态"),
            "checkin_date": data.get("入住日期"),
            "checkout_date": data.get("离店日期"),
            "fetched_at": data.get("数据时效"),
            "summary": summary,
            "items": items,
            "notes": reminders,
        }

    @classmethod
    def _extract_assistant_plan_context(cls, content: str | None) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None

        budget_lines = cls._extract_section_lines(text, {"预算汇总"})
        note_lines = cls._extract_section_lines(text, {"注意事项"})
        assumption_lines = cls._extract_section_lines(text, {"本次假设"})
        reason_lines = cls._extract_section_lines(text, {"推荐理由"})

        cards: list[dict[str, Any]] = []
        payload: dict[str, Any] = {
            "provider": "assistant",
            "version": 1,
            "cards": cards,
        }

        budget = cls._build_budget_payload(budget_lines)
        if budget:
            payload["budget"] = budget
            cards.append(
                cls._build_card(
                    provider="assistant",
                    card_type="budget_summary",
                    title="预算汇总",
                    summary=budget.get("summary") or "已整理预算汇总",
                    data=budget,
                )
            )

        notes = cls._build_list_payload(note_lines, fallback_summary="已整理出行注意事项")
        if notes:
            payload["notes"] = notes
            cards.append(
                cls._build_card(
                    provider="assistant",
                    card_type="travel_notes",
                    title="注意事项",
                    summary=notes.get("summary") or "已整理出行注意事项",
                    data=notes,
                )
            )

        assumptions = cls._build_list_payload(
            assumption_lines,
            fallback_summary="本轮规划使用了默认假设",
        )
        if assumptions:
            payload["assumptions"] = assumptions
            cards.append(
                cls._build_card(
                    provider="assistant",
                    card_type="planning_assumptions",
                    title="本次假设",
                    summary=assumptions.get("summary") or "本轮规划使用了默认假设",
                    data=assumptions,
                )
            )

        reasons = cls._build_list_payload(reason_lines, fallback_summary="已整理本次推荐理由")
        if reasons:
            payload["reasons"] = reasons
            cards.append(
                cls._build_card(
                    provider="assistant",
                    card_type="recommendation_reasons",
                    title="推荐理由",
                    summary=reasons.get("summary") or "已整理本次推荐理由",
                    data=reasons,
                )
            )

        if not cards:
            return None
        return payload

    @classmethod
    def _build_budget_payload(cls, lines: list[str]) -> dict[str, Any] | None:
        cleaned = cls._normalize_section_items(lines)
        if not cleaned:
            return None

        summary = cleaned[0]
        items = cleaned if len(cleaned) > 1 else []
        return {
            "summary": summary,
            "items": items,
        }

    @classmethod
    def _build_list_payload(
        cls,
        lines: list[str],
        *,
        fallback_summary: str,
    ) -> dict[str, Any] | None:
        cleaned = cls._normalize_section_items(lines)
        if not cleaned:
            return None
        summary = cleaned[0] if len(cleaned) == 1 else fallback_summary
        return {
            "summary": summary,
            "items": cleaned,
        }

    @staticmethod
    def _parse_labeled_lines(text: str) -> dict[str, str]:
        data: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- "):
                line = line[2:].strip()
            match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", line)
            if not match:
                continue
            data[match.group("label").strip()] = match.group("value").strip()
        return data

    @classmethod
    def _parse_labeled_section(cls, lines: list[str]) -> dict[str, str]:
        return cls._parse_labeled_lines("\n".join(lines))

    @classmethod
    def _extract_section_lines(cls, text: str, titles: set[str]) -> list[str]:
        lines = text.splitlines()
        collecting = False
        collected: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            heading = cls._HEADING_RE.match(stripped)
            if heading:
                current_title = heading.group("title").strip()
                if collecting:
                    break
                if current_title in titles:
                    collecting = True
                    continue
            if collecting:
                collected.append(raw_line)
        return collected

    @staticmethod
    def _normalize_section_items(lines: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw_line in lines:
            text = raw_line.strip()
            if not text:
                continue
            text = re.sub(r"^[-*]\s*", "", text)
            text = re.sub(r"^\d+\.\s*", "", text)
            text = text.strip()
            if not text:
                continue
            cleaned.append(text)
        return cleaned

    @staticmethod
    def _parse_railway_candidate_items(lines: list[str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current_item: dict[str, Any] | None = None
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r"^(?P<idx>\d+)\.\s+(?P<train>.+)$", line)
            if match:
                current_item = {"train_no": match.group("train").strip()}
                items.append(current_item)
                continue
            if current_item is None or not line.startswith("- "):
                continue
            detail = line[2:].strip()
            label_match = re.match(r"^(?P<label>[^:：]+)[:：]\s*(?P<value>.+)$", detail)
            if not label_match:
                continue
            label = label_match.group("label").strip()
            value = label_match.group("value").strip()
            if label == "站点":
                stations = [part.strip() for part in value.split("->") if part.strip()]
                if stations:
                    current_item["depart_station"] = stations[0]
                if len(stations) > 1:
                    current_item["arrive_station"] = stations[-1]
            elif label == "信息":
                current_item["meta"] = value
        return items
