"""会话意图路由服务。

设计目标：
1. 只负责判断“这条用户输入更像什么会话动作”。
2. 不直接修改数据库状态，避免把“判断”和“执行”耦合在一起。
3. 输出结构化结果，方便后续替换成规则版 + 模型版混合路由。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from db.models import ChatSession, PlanOption
from db.repositories.plan_option_repository import get_active_plan_option, list_plan_options
from domain.plan_option.splitters import extract_mentioned_destinations


@dataclass(slots=True)
class SessionRouteResult:
    """结构化的会话动作路由结果。"""

    action: str
    confidence: float | None = None
    needs_confirmation: bool = False
    target_plan_option_id: uuid.UUID | None = None
    target_plan_option_ids: list[uuid.UUID] = field(default_factory=list)
    mentioned_destinations: list[str] = field(default_factory=list)
    clarification_message: str | None = None

    def to_intent_payload(self) -> dict:
        """给 Web/SSE 层用的轻量结果。"""
        return {
            "action": self.action,
            "confidence": self.confidence,
            "needs_confirmation": self.needs_confirmation,
        }

    def to_event_payload(self) -> dict:
        """给审计事件使用的结构化载荷。"""
        payload = {
            "action": self.action,
            "confidence": self.confidence,
            "needs_confirmation": self.needs_confirmation,
        }
        if self.target_plan_option_id is not None:
            payload["target_plan_option_id"] = str(self.target_plan_option_id)
        if self.target_plan_option_ids:
            payload["target_plan_option_ids"] = [
                str(item) for item in self.target_plan_option_ids
            ]
        if self.mentioned_destinations:
            payload["mentioned_destinations"] = list(self.mentioned_destinations)
        if self.clarification_message:
            payload["clarification_message"] = self.clarification_message
        return payload


class IntentRouter:
    """规则版会话意图路由器。"""

    def __init__(self, db: Session):
        self.db = db

    def route(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        user_input: str,
    ) -> SessionRouteResult:
        """根据当前会话状态，把用户输入路由成一个明确动作。"""
        text = user_input.strip()
        active_plan_option = get_active_plan_option(self.db, session=session)
        plan_options = list_plan_options(self.db, session_id=session.id, user_id=user_id)
        other_options = [
            item
            for item in plan_options
            if active_plan_option is None or item.id != active_plan_option.id
        ]
        mentioned_destinations = extract_mentioned_destinations(text)

        if any(
            keyword in text
            for keyword in ["还记得", "上次", "之前", "以前", "历史方案", "找回"]
        ):
            return SessionRouteResult(
                action="recall_history",
                confidence=0.95,
            )

        if any(
            keyword in text
            for keyword in [
                "就按这个",
                "确定这个方案",
                "保存这个行程",
                "生成正式行程",
                "确认这个方案",
                "作为正式版",
            ]
        ):
            return SessionRouteResult(
                action="finalize_trip",
                confidence=0.96,
            )

        if any(keyword in text for keyword in ["比较", "对比", "哪个更好", "哪个更适合"]):
            target_options = self._pick_options_for_comparison(
                plan_options=plan_options,
                text=text,
            )
            needs_confirmation = len(target_options) < 2
            return SessionRouteResult(
                action="compare_options",
                confidence=0.92 if len(target_options) >= 2 else 0.65,
                target_plan_option_ids=[item.id for item in target_options],
                needs_confirmation=needs_confirmation,
                clarification_message=(
                    "你提到了方案比较，但当前会话里可直接比较的候选方案还不够明确。"
                    " 你可以先保存两版方案，或者明确说要比较哪几个方案。"
                )
                if needs_confirmation
                else None,
            )

        matched_other_option = self._match_option_by_text(other_options, text)
        if matched_other_option and any(
            keyword in text for keyword in ["回到", "切回", "切到", "继续", "看下"]
        ):
            return SessionRouteResult(
                action="switch_to_existing_option",
                confidence=0.94,
                target_plan_option_id=matched_other_option.id,
            )

        if any(
            keyword in text
            for keyword in ["再做一个", "另外做一个", "另一个方案", "再给我一版", "重新做一版"]
        ):
            return SessionRouteResult(
                action="create_new_option",
                confidence=0.93,
            )

        if active_plan_option and mentioned_destinations:
            active_destination = active_plan_option.primary_destination
            different_destinations = [
                city for city in mentioned_destinations if city != active_destination
            ]
            if different_destinations:
                if any(
                    keyword in text for keyword in ["加上", "加入", "顺便", "一起去", "串联"]
                ):
                    return SessionRouteResult(
                        action="expand_current_option",
                        confidence=0.86,
                        mentioned_destinations=different_destinations,
                    )
                return SessionRouteResult(
                    action="update_current_option",
                    confidence=0.48,
                    needs_confirmation=True,
                    mentioned_destinations=different_destinations,
                    clarification_message=(
                        f"你提到了 {different_destinations[0]}。"
                        f" 你是想把它加入当前“{active_plan_option.title}”，"
                        "还是新建一个新的候选方案？"
                    ),
                )

        if active_plan_option and any(
            keyword in text
            for keyword in [
                "改",
                "调整",
                "更新",
                "优化",
                "换成",
                "预算",
                "酒店",
                "路线",
                "细化",
                "补充",
                "完善",
                "丰富",
            ]
        ):
            return SessionRouteResult(
                action="update_current_option",
                confidence=0.82,
            )

        if active_plan_option is not None:
            return SessionRouteResult(
                action="continue_current_option",
                confidence=0.72,
            )

        if plan_options:
            fallback_option = plan_options[0]
            return SessionRouteResult(
                action="switch_to_existing_option",
                confidence=0.65,
                target_plan_option_id=fallback_option.id,
            )

        return SessionRouteResult(
            action="create_new_option",
            confidence=0.68,
        )

    @staticmethod
    def _match_option_by_text(
        options: list[PlanOption],
        text: str,
    ) -> PlanOption | None:
        """按标题/目的地/摘要做轻量文本匹配。"""
        for option in options:
            haystacks = [
                option.title or "",
                option.primary_destination or "",
                option.summary or "",
            ]
            if any(keyword and keyword in text for keyword in haystacks if keyword):
                return option
        return None

    @staticmethod
    def _pick_options_for_comparison(
        *,
        plan_options: list[PlanOption],
        text: str,
    ) -> list[PlanOption]:
        """优先从文本里点名方案；不够时用当前前几项兜底。"""
        target_options: list[PlanOption] = []
        for option in plan_options:
            if option.primary_destination and option.primary_destination in text:
                target_options.append(option)
                continue
            if option.title and option.title in text:
                target_options.append(option)

        if len(target_options) >= 2:
            return target_options
        return plan_options[:3]
