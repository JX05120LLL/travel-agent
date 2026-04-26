import unittest
import uuid
from unittest.mock import MagicMock, patch

from db.models import ChatSession, Message
from services.memory_service import MemoryService, RUNTIME_CONTEXT_TOTAL_MAX_LENGTH


class MemoryServiceTests(unittest.TestCase):
    @patch("services.memory_service.list_plan_options")
    @patch("services.memory_service.list_active_user_preferences")
    @patch("services.memory_service.get_active_comparison")
    @patch("services.memory_service.get_active_plan_option")
    @patch("services.memory_service.list_messages")
    def test_build_runtime_context_messages_includes_preference_and_recall_sections(
        self,
        list_messages,
        get_active_plan_option,
        get_active_comparison,
        list_active_user_preferences,
        list_plan_options,
    ):
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="成都工作区",
            summary="当前正在细化成都方案",
        )
        recent_message = Message(
            id=uuid.uuid4(),
            session_id=session.id,
            user_id=session.user_id,
            role="user",
            content="这次预算有限，尽量轻松一点",
            sequence_no=1,
        )

        list_messages.return_value = [recent_message]
        get_active_plan_option.return_value = None
        get_active_comparison.return_value = None
        list_active_user_preferences.return_value = []
        list_plan_options.return_value = []

        service = MemoryService(db=MagicMock())
        service.preference_service.build_injection_context = MagicMock(
            return_value={
                "current_explicit": [],
                "current_inferred": [],
                "effective_preferences": [],
                "suppressed_preferences": [],
                "summary": "本轮用户明确提出的新偏好：\n- budget.level: 预算偏经济",
            }
        )

        messages = service.build_runtime_context_messages(
            session=session,
            current_user_input="这次预算有限，尽量轻松一点",
            recall_result={
                "summary": "命中了成都亲子行程，可作为当前轮参考",
                "grouped_matches": {
                    "strong_history": [
                        {
                            "title": "成都亲子正式行程",
                            "summary": "三天两晚，节奏轻松",
                            "reasons": ["目的地匹配:成都"],
                        }
                    ],
                    "candidate_options": [],
                    "relevant_preferences": [],
                    "related_sessions": [],
                },
            },
            extra_sections=["【本轮工作区动作】\n已切到当前方案"],
        )

        self.assertGreaterEqual(len(messages), 2)
        system_message = messages[0]
        self.assertIn("【用户长期偏好】", system_message.content)
        self.assertIn("预算偏经济", system_message.content)
        self.assertIn("【本轮历史召回】", system_message.content)
        self.assertIn("可优先复用的历史正式行程 / 已成型方案", system_message.content)
        self.assertIn("成都亲子正式行程", system_message.content)
        self.assertIn("【本轮工作区动作】", system_message.content)

        _, kwargs = service.preference_service.build_injection_context.call_args
        self.assertEqual("这次预算有限，尽量轻松一点", kwargs["current_input"])

    @patch("services.memory_service.list_plan_options")
    @patch("services.memory_service.list_active_user_preferences")
    @patch("services.memory_service.get_active_comparison")
    @patch("services.memory_service.get_active_plan_option")
    @patch("services.memory_service.list_messages")
    def test_build_runtime_context_messages_applies_section_priority_budget(
        self,
        list_messages,
        get_active_plan_option,
        get_active_comparison,
        list_active_user_preferences,
        list_plan_options,
    ):
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="北京工作区",
            summary="当前正在细化北京方案",
            latest_user_message="继续完善北京路线",
        )
        recent_message = Message(
            id=uuid.uuid4(),
            session_id=session.id,
            user_id=session.user_id,
            role="user",
            content="继续完善北京路线",
            sequence_no=1,
        )
        active_plan_option = MagicMock()
        active_plan_option.id = uuid.uuid4()
        active_plan_option.title = "北京主方案"
        active_plan_option.status = "selected"
        active_plan_option.primary_destination = "北京"
        active_plan_option.total_days = 3
        active_plan_option.travel_start_date = None
        active_plan_option.travel_end_date = None
        active_plan_option.summary = "北京主线方案"
        active_plan_option.plan_markdown = None

        list_messages.return_value = [recent_message]
        get_active_plan_option.return_value = active_plan_option
        get_active_comparison.return_value = None
        list_active_user_preferences.return_value = []
        list_plan_options.return_value = [active_plan_option]

        service = MemoryService(db=MagicMock())
        service.preference_service.build_injection_context = MagicMock(
            return_value={
                "current_explicit": [],
                "current_inferred": [],
                "effective_preferences": [],
                "suppressed_preferences": [],
                "summary": "本轮用户明确提出的新偏好：\n- pace.style: 偏轻松慢节奏",
            }
        )

        context = {
            "session_id": str(session.id),
            "session_summary": session.summary,
            "active_plan_option_id": str(active_plan_option.id),
            "active_plan_title": active_plan_option.title,
            "active_plan_summary": (
                "方案标题：北京主方案\n"
                "方案状态：selected\n"
                "主目的地：北京\n"
                "总天数：3 天\n"
                "当前方案摘要：北京主线方案"
            ),
            "active_comparison_id": None,
            "active_comparison_summary": None,
            "user_preference_summary": "本轮用户明确提出的新偏好：\n- pace.style: 偏轻松慢节奏",
            "user_preference_context": {
                "current_explicit": [],
                "current_inferred": [],
                "effective_preferences": [],
                "suppressed_preferences": [],
                "summary": "本轮用户明确提出的新偏好：\n- pace.style: 偏轻松慢节奏",
            },
            "recent_messages": [recent_message],
            "plan_summaries": [
                {
                    "id": str(active_plan_option.id),
                    "title": "北京主方案",
                    "status": "selected",
                    "primary_destination": "北京",
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "上海备选",
                    "status": "draft",
                    "primary_destination": "上海",
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "杭州备选",
                    "status": "draft",
                    "primary_destination": "杭州",
                },
            ],
        }

        service.build_session_context_payload = MagicMock(return_value=context)
        messages = service.build_runtime_context_messages(
            session=session,
            current_user_input="继续完善北京路线",
            recall_result={
                "summary": "命中了北京历史方案",
                "grouped_matches": {
                    "strong_history": [
                        {
                            "title": "北京历史正式行程",
                            "summary": "三天主线",
                            "reasons": ["目的地匹配:北京"],
                        }
                    ],
                    "candidate_options": [],
                    "relevant_preferences": [],
                    "related_sessions": [],
                },
            },
            extra_sections=[
                "【本轮工作区动作】\n已切换到北京主方案",
                "【本轮澄清结论】\n用户希望继续细化，不新建分支",
                "【本轮执行约束】\n优先保留原有日期范围",
                "【本轮输出要求】\n先补每天安排，再补酒店建议",
            ],
        )

        system_message = messages[0]
        self.assertIn("【当前激活方案记忆】", system_message.content)
        self.assertIn("【本轮工作区动作】", system_message.content)
        self.assertIn("【本轮输出要求】", system_message.content)
        self.assertIn("【当前会话摘要】", system_message.content)
        self.assertNotIn("【当前工作区内的其他候选方案】", system_message.content)
        self.assertNotIn("【用户长期偏好】", system_message.content)
        self.assertNotIn("【本轮历史召回】", system_message.content)

    def test_build_runtime_context_messages_deduplicates_sections_and_caps_total_length(
        self,
    ):
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="东京工作区",
            summary="当前正在整理东京周末短途方案",
            latest_user_message="继续保留周末轻松节奏",
        )
        recent_message = Message(
            id=uuid.uuid4(),
            session_id=session.id,
            user_id=session.user_id,
            role="user",
            content="继续保留周末轻松节奏",
            sequence_no=1,
        )

        duplicated_constraint = (
            "【本轮执行约束】\n"
            + "优先保留周末慢节奏、减少跨城折返，并尽量沿用当前酒店片区。 " * 20
        )
        long_plan_summary = (
            "方案标题：东京周末主方案\n"
            "方案状态：selected\n"
            "主目的地：东京\n"
            "当前方案摘要："
            + ("东京周末慢节奏亲子出行，优先浅草、上野、银座片区。 " * 80)
        )
        long_preference_summary = "本轮用户明确提出的新偏好：\n- pace.style: 偏轻松慢节奏\n" + (
            "补充说明：倾向少换酒店、少折返、避免过满日程。 " * 40
        )

        context = {
            "session_id": str(session.id),
            "session_summary": session.summary,
            "active_plan_option_id": str(uuid.uuid4()),
            "active_plan_title": "东京周末主方案",
            "active_plan_summary": long_plan_summary,
            "active_comparison_id": None,
            "active_comparison_summary": None,
            "user_preference_summary": long_preference_summary,
            "user_preference_context": {
                "current_explicit": [],
                "current_inferred": [],
                "effective_preferences": [],
                "suppressed_preferences": [],
                "summary": long_preference_summary,
            },
            "recent_messages": [recent_message],
            "plan_summaries": [
                {
                    "id": str(uuid.uuid4()),
                    "title": "东京周末主方案",
                    "status": "selected",
                    "primary_destination": "东京",
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "箱根备选",
                    "status": "draft",
                    "primary_destination": "箱根",
                },
            ],
        }

        service = MemoryService(db=MagicMock())
        service.build_session_context_payload = MagicMock(return_value=context)

        messages = service.build_runtime_context_messages(
            session=session,
            current_user_input="继续保留周末轻松节奏",
            recall_result={
                "summary": "命中了东京周末历史短途方案，可复用慢节奏安排。 " * 30,
                "grouped_matches": {},
            },
            extra_sections=[
                duplicated_constraint,
                duplicated_constraint,
                "【本轮输出要求】\n先补每天安排，再补酒店建议。 " * 20,
            ],
        )

        system_message = messages[0]
        self.assertEqual(1, system_message.content.count("【本轮执行约束】"))
        self.assertLessEqual(len(system_message.content), RUNTIME_CONTEXT_TOTAL_MAX_LENGTH)
        self.assertIn("【当前激活方案记忆】", system_message.content)
        self.assertIn("【本轮输出要求】", system_message.content)


if __name__ == "__main__":
    unittest.main()
