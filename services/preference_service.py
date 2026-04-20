"""用户长期偏好服务。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from db.models import UserPreference
from db.repositories.preference_repository import (
    get_user_preference,
    list_active_user_preferences,
)
from domain.memory.preference_rules import PreferenceCandidate, extract_preference_candidates

PREFERENCE_INJECTION_LIMIT = 8


class PreferenceService:
    """负责长期偏好的查询、提取、合并与注入前整理。"""

    def __init__(self, db: Session):
        self.db = db

    def list_active_preferences(
        self,
        *,
        user_id: uuid.UUID,
        limit: int | None = 8,
    ) -> list[UserPreference]:
        """列出当前用户的长期偏好。"""
        return list_active_user_preferences(self.db, user_id=user_id, limit=limit)

    def remember_from_message(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        message_id: uuid.UUID,
        text: str,
    ) -> list[UserPreference]:
        """把用户消息里可复用的稳定偏好沉淀为长期记忆。"""
        candidates = extract_preference_candidates(text)
        remembered: list[UserPreference] = []

        for item in candidates:
            preference = get_user_preference(
                self.db,
                user_id=user_id,
                category=item.category,
                key=item.key,
            )
            if preference is None:
                preference = UserPreference(
                    user_id=user_id,
                    preference_category=item.category,
                    preference_key=item.key,
                    preference_value=item.value,
                    source=item.source,
                    confidence=item.confidence,
                    source_session_id=session_id,
                    source_message_id=message_id,
                    last_confirmed_at=(
                        datetime.now() if item.source == "user_explicit" else None
                    ),
                )
                self.db.add(preference)
                remembered.append(preference)
                continue

            if not self._should_update_preference(preference=preference, candidate=item):
                remembered.append(preference)
                continue

            preference.preference_value = item.value
            preference.source = item.source
            preference.confidence = item.confidence
            preference.is_active = True
            preference.source_session_id = session_id
            preference.source_message_id = message_id
            if item.source == "user_explicit":
                preference.last_confirmed_at = datetime.now()
            remembered.append(preference)

        if remembered:
            self.db.flush()

        return remembered

    def build_injection_summary(
        self,
        *,
        preferences: list[UserPreference],
        current_input: str | None = None,
        limit: int = PREFERENCE_INJECTION_LIMIT,
    ) -> str | None:
        """生成更适合注入给模型的偏好摘要。"""
        context = self.build_injection_context(
            preferences=preferences,
            current_input=current_input,
            limit=limit,
        )
        return context["summary"]

    def build_injection_context(
        self,
        *,
        preferences: list[UserPreference],
        current_input: str | None = None,
        limit: int = PREFERENCE_INJECTION_LIMIT,
    ) -> dict:
        """把长期偏好和当前轮偏好整理成可注入上下文。"""
        sorted_preferences = self._sort_preferences(preferences)[:limit]
        current_candidates = extract_preference_candidates(current_input or "")
        current_explicit: list[PreferenceCandidate] = []
        current_inferred: list[PreferenceCandidate] = []
        suppressed_identities: set[str] = set()
        preference_map = {
            self._preference_identity(item): item for item in sorted_preferences
        }

        for candidate in current_candidates:
            matched_preference = preference_map.get(candidate.identity)
            if candidate.source == "user_explicit":
                current_explicit.append(candidate)
                if (
                    matched_preference is None
                    or self._is_conflicting(
                        preference=matched_preference,
                        candidate=candidate,
                    )
                ):
                    suppressed_identities.add(candidate.identity)
                continue

            if (
                matched_preference is not None
                and matched_preference.source == "user_explicit"
                and Decimal(str(matched_preference.confidence or 0)) > candidate.confidence
            ):
                continue

            current_inferred.append(candidate)
            if (
                matched_preference is not None
                and self._is_conflicting(
                    preference=matched_preference,
                    candidate=candidate,
                )
            ):
                suppressed_identities.add(candidate.identity)

        effective_preferences: list[UserPreference] = []
        suppressed_preferences: list[UserPreference] = []
        for item in sorted_preferences:
            if self._preference_identity(item) in suppressed_identities:
                suppressed_preferences.append(item)
            else:
                effective_preferences.append(item)

        summary = self._build_preference_injection_summary(
            current_explicit=current_explicit,
            current_inferred=current_inferred,
            effective_preferences=effective_preferences,
            suppressed_preferences=suppressed_preferences,
        )
        return {
            "current_explicit": current_explicit,
            "current_inferred": current_inferred,
            "effective_preferences": effective_preferences,
            "suppressed_preferences": suppressed_preferences,
            "summary": summary,
        }

    @staticmethod
    def _should_update_preference(
        *,
        preference: UserPreference,
        candidate: PreferenceCandidate,
    ) -> bool:
        """控制已有偏好是否应被新证据覆盖。"""
        existing_confidence = Decimal(str(preference.confidence or 0))

        if not preference.is_active:
            return True
        if candidate.source == "user_explicit" and preference.source != "user_explicit":
            return True
        if (
            preference.source == "user_explicit"
            and candidate.source != "user_explicit"
            and existing_confidence > candidate.confidence
        ):
            return False
        return candidate.confidence >= existing_confidence

    @staticmethod
    def _sort_preferences(preferences: list[UserPreference]) -> list[UserPreference]:
        """按显式优先、置信度优先的顺序整理偏好。"""
        return sorted(
            preferences,
            key=lambda item: (
                0 if item.source == "user_explicit" else 1,
                -float(item.confidence or 0),
                -(item.updated_at.timestamp() if item.updated_at else 0),
            ),
            reverse=False,
        )

    @staticmethod
    def _preference_identity(preference: UserPreference) -> str:
        return f"{preference.preference_category}.{preference.preference_key}"

    @staticmethod
    def _display_preference_value(value: dict | None) -> str:
        if not value:
            return "已记录"
        if "label" in value:
            return str(value["label"])
        if "value" in value:
            return str(value["value"])
        return str(value)

    def _build_preference_injection_summary(
        self,
        *,
        current_explicit: list[PreferenceCandidate],
        current_inferred: list[PreferenceCandidate],
        effective_preferences: list[UserPreference],
        suppressed_preferences: list[UserPreference],
    ) -> str | None:
        if not (
            current_explicit
            or current_inferred
            or effective_preferences
            or suppressed_preferences
        ):
            return None

        lines: list[str] = []
        if current_explicit:
            lines.append("本轮用户明确提出的新偏好：")
            lines.extend(
                f"- {item.identity}: {self._display_preference_value(item.value)}"
                for item in current_explicit
            )
            lines.append("如与长期偏好冲突，以本轮明确要求为准。")

        if current_inferred:
            lines.append("本轮可参考的即时偏好倾向：")
            lines.extend(
                f"- {item.identity}: {self._display_preference_value(item.value)}"
                for item in current_inferred
            )

        if effective_preferences:
            lines.append("可延续的长期稳定偏好：")
            lines.extend(
                (
                    f"- {self._preference_identity(item)}: "
                    f"{self._display_preference_value(item.preference_value)} "
                    f"(置信度 {Decimal(str(item.confidence or 0)):.2f})"
                )
                for item in effective_preferences
            )

        if suppressed_preferences:
            lines.append("以下长期偏好与本轮要求冲突，本轮暂不沿用：")
            lines.extend(
                f"- {self._preference_identity(item)}: "
                f"{self._display_preference_value(item.preference_value)}"
                for item in suppressed_preferences
            )

        return "\n".join(lines)

    def _is_conflicting(
        self,
        *,
        preference: UserPreference,
        candidate: PreferenceCandidate,
    ) -> bool:
        return (
            self._display_preference_value(preference.preference_value).strip()
            != self._display_preference_value(candidate.value).strip()
        )
