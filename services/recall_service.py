"""历史召回服务。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from db.models import HistoryRecallLog
from db.repositories.plan_option_repository import list_user_plan_options_for_recall
from db.repositories.preference_repository import list_active_user_preferences
from db.repositories.recall_repository import (
    add_history_recall_log,
    list_history_recall_logs,
)
from db.repositories.session_repository import list_user_sessions_for_recall
from db.repositories.trip_repository import list_user_trips
from domain.recall.ranking import build_query_profile, score_recall_candidate
from domain.plan_option.splitters import build_plan_summary, extract_mentioned_destinations
from tools.holiday_calendar import contains_holiday_keyword, resolve_holiday_window


class RecallService:
    """负责跨会话历史召回及日志记录。"""

    def __init__(self, db: Session):
        self.db = db

    def list_recall_logs(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
        limit: int = 20,
    ):
        """列出历史召回日志。"""
        return list_history_recall_logs(
            self.db,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
        )

    def search_history(
        self,
        *,
        user_id: uuid.UUID,
        query_text: str,
        session_id: uuid.UUID | None = None,
        limit: int = 5,
    ) -> dict:
        """按用户维度做更稳的跨会话历史召回。"""
        holiday_window = None
        if contains_holiday_keyword(query_text):
            try:
                holiday_window = resolve_holiday_window(query_text)
            except Exception:
                holiday_window = None

        profile = build_query_profile(
            query_text,
            holiday_window=holiday_window,
        )
        matches: list[dict] = []

        for trip in list_user_trips(
            self.db,
            user_id=user_id,
            exclude_session_id=session_id,
        ):
            trip_preference_facts = self._extract_structured_preference_facts(
                getattr(trip, "preferences", {}) or {}
            )
            score, reasons = score_recall_candidate(
                profile,
                candidate_texts=[
                    trip.title,
                    trip.primary_destination,
                    trip.summary,
                    trip.plan_markdown,
                ],
                base_score=0.35,
                candidate_destinations=[
                    item.destination_name
                    for item in getattr(trip, "destinations", [])
                    if item.destination_name
                ]
                or extract_mentioned_destinations(
                    trip.primary_destination,
                    trip.title,
                    trip.plan_markdown,
                ),
                candidate_preference_facts=trip_preference_facts,
                candidate_preference_identities=set(trip_preference_facts.keys()),
                candidate_day_count=getattr(trip, "total_days", None),
                candidate_start_date=getattr(trip, "travel_start_date", None),
                candidate_end_date=getattr(trip, "travel_end_date", None),
            )
            if score < 0.45:
                continue
            matches.append(
                {
                    "record_type": "trip",
                    "record_id": str(trip.id),
                    "title": trip.title,
                    "summary": trip.summary or build_plan_summary(trip.plan_markdown or trip.title),
                    "score": score,
                    "reasons": reasons,
                }
            )

        for option in list_user_plan_options_for_recall(
            self.db,
            user_id=user_id,
            exclude_session_id=session_id,
        ):
            option_preference_facts = self._extract_structured_preference_facts(
                option.preferences or {}
            )
            score, reasons = score_recall_candidate(
                profile,
                candidate_texts=[
                    option.title,
                    option.primary_destination,
                    option.summary,
                    option.plan_markdown,
                ],
                base_score=0.30,
                candidate_destinations=extract_mentioned_destinations(
                    option.primary_destination,
                    option.title,
                    option.plan_markdown,
                ),
                candidate_preference_facts=option_preference_facts,
                candidate_preference_identities=set(option_preference_facts.keys()),
                candidate_day_count=getattr(option, "total_days", None),
                candidate_start_date=getattr(option, "travel_start_date", None),
                candidate_end_date=getattr(option, "travel_end_date", None),
            )
            if score < 0.45:
                continue
            matches.append(
                {
                    "record_type": "plan_option",
                    "record_id": str(option.id),
                    "title": option.title,
                    "summary": option.summary
                    or build_plan_summary(option.plan_markdown or option.title),
                    "score": score,
                    "reasons": reasons,
                }
            )

        for past_session in list_user_sessions_for_recall(
            self.db,
            user_id=user_id,
            exclude_session_id=session_id,
        ):
            score, reasons = score_recall_candidate(
                profile,
                candidate_texts=[
                    past_session.title,
                    past_session.summary,
                    past_session.latest_user_message,
                ],
                base_score=0.22,
            )
            if score < 0.45:
                continue
            matches.append(
                {
                    "record_type": "session",
                    "record_id": str(past_session.id),
                    "title": past_session.title,
                    "summary": past_session.summary
                    or (past_session.latest_user_message or "")[:160],
                    "score": score,
                    "reasons": reasons,
                }
            )

        for preference in list_active_user_preferences(
            self.db,
            user_id=user_id,
            limit=None,
        ):
            preference_identity = {
                f"{preference.preference_category}.{preference.preference_key}"
            }
            score, reasons = score_recall_candidate(
                profile,
                candidate_texts=[
                    preference.preference_category,
                    preference.preference_key,
                    str(preference.preference_value.get("label") or ""),
                    str(preference.preference_value.get("evidence") or ""),
                ],
                base_score=0.28,
                candidate_preference_identities=preference_identity,
            )
            if score < 0.48:
                continue
            matches.append(
                {
                    "record_type": "preference",
                    "record_id": str(preference.id),
                    "title": f"{preference.preference_category}.{preference.preference_key}",
                    "summary": str(preference.preference_value.get("label") or preference.preference_value),
                    "score": score,
                    "reasons": reasons,
                }
            )

        matches.sort(key=lambda item: item["score"], reverse=True)
        matches = matches[:limit]
        top = matches[0] if matches else None
        confidence = top["score"] if top else 0
        grouped_matches = self._group_matches(matches)
        injection_section = self._build_injection_section(grouped_matches)

        if not matches:
            recall_type = "none"
            summary = "未找到明显匹配的历史记录，可以基于你现在的需求重新规划。"
        elif len(matches) == 1 or (
            len(matches) > 1 and matches[0]["score"] - matches[1]["score"] >= 0.18
        ):
            recall_type = top["record_type"]
            reason_text = "；".join(top.get("reasons") or [])
            summary = (
                f"已召回历史{top['record_type']}：{top['title']}。\n"
                f"摘要：{top['summary'] or '暂无摘要'}"
            )
            if reason_text:
                summary += f"\n命中原因：{reason_text}"
        else:
            recall_type = top["record_type"]
            candidate_lines = [
                (
                    f"- {item['title']}（{item['record_type']}，匹配度 {item['score']:.2f}"
                    + (f"，命中 { '；'.join(item.get('reasons') or []) }" if item.get("reasons") else "")
                    + "）"
                )
                for item in matches[:3]
            ]
            summary = "找到多条相近的历史记录，请优先按下面候选理解当前问题：\n" + "\n".join(
                candidate_lines
            )

        recall_log = HistoryRecallLog(
            user_id=user_id,
            session_id=session_id,
            query_text=query_text,
            recall_type=(
                recall_type
                if recall_type in {"trip", "plan_option", "session", "preference"}
                else "none"
            ),
            matched_record_type=top["record_type"] if top else None,
            matched_record_id=uuid.UUID(top["record_id"]) if top else None,
            matched_count=len(matches),
            confidence=confidence or None,
            recall_payload={"matches": matches, "summary": summary},
        )
        recall_log.recall_payload = {
            "matches": matches,
            "grouped_matches": grouped_matches,
            "summary": summary,
            "injection_section": injection_section,
            "holiday_window": holiday_window,
        }
        add_history_recall_log(self.db, recall_log)

        return {
            "summary": summary,
            "matches": matches,
            "grouped_matches": grouped_matches,
            "confidence": confidence,
            "injection_section": injection_section,
            "log_id": str(recall_log.id),
        }

    @staticmethod
    def _extract_structured_preference_facts(preferences: dict) -> dict[str, str]:
        """把结构化 preferences JSON 压缩成 identity -> value 的稳定事实映射。"""
        if not isinstance(preferences, dict):
            return {}

        facts: dict[str, str] = {}

        def walk(node: dict, prefix: str = "") -> None:
            for key, value in node.items():
                current_key = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, dict):
                    if "value" in value and value["value"] not in (None, ""):
                        facts[current_key] = str(value["value"]).strip().lower()
                    walk(value, current_key)
                    continue
                if value in (None, "", False, [], {}):
                    continue
                facts[current_key] = str(value).strip().lower()

        walk(preferences)
        return facts

    @staticmethod
    def _group_matches(matches: list[dict]) -> dict[str, list[dict]]:
        """按注入用途而不是底层表类型，对召回结果做分组。"""
        grouped = {
            "strong_history": [],
            "candidate_options": [],
            "relevant_preferences": [],
            "related_sessions": [],
        }
        for item in matches:
            record_type = item.get("record_type")
            if record_type == "trip":
                grouped["strong_history"].append(item)
            elif record_type == "plan_option":
                grouped["candidate_options"].append(item)
            elif record_type == "preference":
                grouped["relevant_preferences"].append(item)
            elif record_type == "session":
                grouped["related_sessions"].append(item)
        return grouped

    def _build_injection_section(self, grouped_matches: dict[str, list[dict]]) -> str:
        """生成给模型使用的结构化历史召回注入段。"""
        if not any(grouped_matches.values()):
            return (
                "【本轮历史召回】\n"
                "未找到可直接复用的跨会话历史，请基于当前输入继续确认，"
                "不要假设之前已经有确定结论。"
            )

        lines = [
            "【本轮历史召回】",
            "以下内容来自其他会话或历史记录，仅供参考；若与本轮用户明确要求冲突，以本轮要求为准。",
            "若命中同一目的地、同一时间窗、同一偏好约束，可优先复用其中已验证过的安排思路；"
            "若只命中部分特征，则只把它当作参考样例，不要直接当成当前结论。",
        ]

        if grouped_matches["strong_history"]:
            lines.append("强相关的正式行程 / 已成型历史方案：")
            lines.extend(
                self._format_injection_line(item)
                for item in grouped_matches["strong_history"][:2]
            )

        if grouped_matches["candidate_options"]:
            lines.append("可参考的历史候选方案：")
            lines.extend(
                self._format_injection_line(item)
                for item in grouped_matches["candidate_options"][:3]
            )

        if grouped_matches["relevant_preferences"]:
            lines.append("命中的相关长期偏好：")
            lines.extend(
                self._format_injection_line(item)
                for item in grouped_matches["relevant_preferences"][:3]
            )

        if grouped_matches["related_sessions"]:
            lines.append("相关历史会话：")
            lines.extend(
                self._format_injection_line(item)
                for item in grouped_matches["related_sessions"][:2]
            )

        return "\n".join(lines)

    @staticmethod
    def _format_injection_line(item: dict) -> str:
        """把单条召回结果压缩成一行，便于模型快速利用。"""
        title = str(item.get("title") or "未命名记录").strip()
        summary = str(item.get("summary") or "暂无摘要").strip()
        reasons = "、".join(item.get("reasons") or [])
        score = float(item.get("score") or 0)
        line = f"- [{item.get('record_type')}] {title}：{summary}（匹配度 {score:.2f}）"
        if reasons:
            line += f"；命中原因：{reasons}"
        return line
