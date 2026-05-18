import unittest
import uuid
from unittest.mock import MagicMock, patch

from db.models import ChatSession, Message
from services.chat.memory_service import MemoryService, RUNTIME_CONTEXT_TOTAL_MAX_LENGTH


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
            title="鎴愰兘宸ヤ綔鍖?,
            summary="褰撳墠姝ｅ湪缁嗗寲鎴愰兘鏂规",
        )
        recent_message = Message(
            id=uuid.uuid4(),
            session_id=session.id,
            user_id=session.user_id,
            role="user",
            content="杩欐棰勭畻鏈夐檺锛屽敖閲忚交鏉句竴鐐?,
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
                "summary": "鏈疆鐢ㄦ埛鏄庣‘鎻愬嚭鐨勬柊鍋忓ソ锛歕n- budget.level: 棰勭畻鍋忕粡娴?,
            }
        )

        messages = service.build_runtime_context_messages(
            session=session,
            current_user_input="杩欐棰勭畻鏈夐檺锛屽敖閲忚交鏉句竴鐐?,
            recall_result={
                "summary": "鍛戒腑浜嗘垚閮戒翰瀛愯绋嬶紝鍙綔涓哄綋鍓嶈疆鍙傝€?,
                "grouped_matches": {
                    "strong_history": [
                        {
                            "title": "鎴愰兘浜插瓙姝ｅ紡琛岀▼",
                            "summary": "涓夊ぉ涓ゆ櫄锛岃妭濂忚交鏉?,
                            "reasons": ["鐩殑鍦板尮閰?鎴愰兘"],
                        }
                    ],
                    "candidate_options": [],
                    "relevant_preferences": [],
                    "related_sessions": [],
                },
            },
            extra_sections=["銆愭湰杞伐浣滃尯鍔ㄤ綔銆慭n宸插垏鍒板綋鍓嶆柟妗?],
        )

        self.assertGreaterEqual(len(messages), 2)
        system_message = messages[0]
        self.assertIn("銆愮敤鎴烽暱鏈熷亸濂姐€?, system_message.content)
        self.assertIn("棰勭畻鍋忕粡娴?, system_message.content)
        self.assertIn("銆愭湰杞巻鍙插彫鍥炪€?, system_message.content)
        self.assertIn("鍙紭鍏堝鐢ㄧ殑鍘嗗彶姝ｅ紡琛岀▼ / 宸叉垚鍨嬫柟妗?, system_message.content)
        self.assertIn("鎴愰兘浜插瓙姝ｅ紡琛岀▼", system_message.content)
        self.assertIn("銆愭湰杞伐浣滃尯鍔ㄤ綔銆?, system_message.content)

        _, kwargs = service.preference_service.build_injection_context.call_args
        self.assertEqual("杩欐棰勭畻鏈夐檺锛屽敖閲忚交鏉句竴鐐?, kwargs["current_input"])

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
            title="鍖椾含宸ヤ綔鍖?,
            summary="褰撳墠姝ｅ湪缁嗗寲鍖椾含鏂规",
            latest_user_message="缁х画瀹屽杽鍖椾含璺嚎",
        )
        recent_message = Message(
            id=uuid.uuid4(),
            session_id=session.id,
            user_id=session.user_id,
            role="user",
            content="缁х画瀹屽杽鍖椾含璺嚎",
            sequence_no=1,
        )
        active_plan_option = MagicMock()
        active_plan_option.id = uuid.uuid4()
        active_plan_option.title = "鍖椾含涓绘柟妗?
        active_plan_option.status = "selected"
        active_plan_option.primary_destination = "鍖椾含"
        active_plan_option.total_days = 3
        active_plan_option.travel_start_date = None
        active_plan_option.travel_end_date = None
        active_plan_option.summary = "鍖椾含涓荤嚎鏂规"
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
                "summary": "鏈疆鐢ㄦ埛鏄庣‘鎻愬嚭鐨勬柊鍋忓ソ锛歕n- pace.style: 鍋忚交鏉炬參鑺傚",
            }
        )

        context = {
            "session_id": str(session.id),
            "session_summary": session.summary,
            "active_plan_option_id": str(active_plan_option.id),
            "active_plan_title": active_plan_option.title,
            "active_plan_summary": (
                "鏂规鏍囬锛氬寳浜富鏂规\n"
                "鏂规鐘舵€侊細selected\n"
                "涓荤洰鐨勫湴锛氬寳浜琝n"
                "鎬诲ぉ鏁帮細3 澶‐n"
                "褰撳墠鏂规鎽樿锛氬寳浜富绾挎柟妗?
            ),
            "active_comparison_id": None,
            "active_comparison_summary": None,
            "user_preference_summary": "鏈疆鐢ㄦ埛鏄庣‘鎻愬嚭鐨勬柊鍋忓ソ锛歕n- pace.style: 鍋忚交鏉炬參鑺傚",
            "user_preference_context": {
                "current_explicit": [],
                "current_inferred": [],
                "effective_preferences": [],
                "suppressed_preferences": [],
                "summary": "鏈疆鐢ㄦ埛鏄庣‘鎻愬嚭鐨勬柊鍋忓ソ锛歕n- pace.style: 鍋忚交鏉炬參鑺傚",
            },
            "recent_messages": [recent_message],
            "plan_summaries": [
                {
                    "id": str(active_plan_option.id),
                    "title": "鍖椾含涓绘柟妗?,
                    "status": "selected",
                    "primary_destination": "鍖椾含",
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "涓婃捣澶囬€?,
                    "status": "draft",
                    "primary_destination": "涓婃捣",
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "鏉窞澶囬€?,
                    "status": "draft",
                    "primary_destination": "鏉窞",
                },
            ],
        }

        service.build_session_context_payload = MagicMock(return_value=context)
        messages = service.build_runtime_context_messages(
            session=session,
            current_user_input="缁х画瀹屽杽鍖椾含璺嚎",
            recall_result={
                "summary": "鍛戒腑浜嗗寳浜巻鍙叉柟妗?,
                "grouped_matches": {
                    "strong_history": [
                        {
                            "title": "鍖椾含鍘嗗彶姝ｅ紡琛岀▼",
                            "summary": "涓夊ぉ涓荤嚎",
                            "reasons": ["鐩殑鍦板尮閰?鍖椾含"],
                        }
                    ],
                    "candidate_options": [],
                    "relevant_preferences": [],
                    "related_sessions": [],
                },
            },
            extra_sections=[
                "銆愭湰杞伐浣滃尯鍔ㄤ綔銆慭n宸插垏鎹㈠埌鍖椾含涓绘柟妗?,
                "銆愭湰杞緞娓呯粨璁恒€慭n鐢ㄦ埛甯屾湜缁х画缁嗗寲锛屼笉鏂板缓鍒嗘敮",
                "銆愭湰杞墽琛岀害鏉熴€慭n浼樺厛淇濈暀鍘熸湁鏃ユ湡鑼冨洿",
                "銆愭湰杞緭鍑鸿姹傘€慭n鍏堣ˉ姣忓ぉ瀹夋帓锛屽啀琛ラ厭搴楀缓璁?,
            ],
        )

        system_message = messages[0]
        self.assertIn("銆愬綋鍓嶆縺娲绘柟妗堣蹇嗐€?, system_message.content)
        self.assertIn("銆愭湰杞伐浣滃尯鍔ㄤ綔銆?, system_message.content)
        self.assertIn("銆愭湰杞緭鍑鸿姹傘€?, system_message.content)
        self.assertIn("銆愬綋鍓嶄細璇濇憳瑕併€?, system_message.content)
        self.assertNotIn("銆愬綋鍓嶅伐浣滃尯鍐呯殑鍏朵粬鍊欓€夋柟妗堛€?, system_message.content)
        self.assertNotIn("銆愮敤鎴烽暱鏈熷亸濂姐€?, system_message.content)
        self.assertNotIn("銆愭湰杞巻鍙插彫鍥炪€?, system_message.content)

    def test_build_runtime_context_messages_deduplicates_sections_and_caps_total_length(
        self,
    ):
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="涓滀含宸ヤ綔鍖?,
            summary="褰撳墠姝ｅ湪鏁寸悊涓滀含鍛ㄦ湯鐭€旀柟妗?,
            latest_user_message="缁х画淇濈暀鍛ㄦ湯杞绘澗鑺傚",
        )
        recent_message = Message(
            id=uuid.uuid4(),
            session_id=session.id,
            user_id=session.user_id,
            role="user",
            content="缁х画淇濈暀鍛ㄦ湯杞绘澗鑺傚",
            sequence_no=1,
        )

        duplicated_constraint = (
            "銆愭湰杞墽琛岀害鏉熴€慭n"
            + "浼樺厛淇濈暀鍛ㄦ湯鎱㈣妭濂忋€佸噺灏戣法鍩庢姌杩旓紝骞跺敖閲忔部鐢ㄥ綋鍓嶉厭搴楃墖鍖恒€?" * 20
        )
        long_plan_summary = (
            "鏂规鏍囬锛氫笢浜懆鏈富鏂规\n"
            "鏂规鐘舵€侊細selected\n"
            "涓荤洰鐨勫湴锛氫笢浜琝n"
            "褰撳墠鏂规鎽樿锛?
            + ("涓滀含鍛ㄦ湯鎱㈣妭濂忎翰瀛愬嚭琛岋紝浼樺厛娴呰崏銆佷笂閲庛€侀摱搴х墖鍖恒€?" * 80)
        )
        long_preference_summary = "鏈疆鐢ㄦ埛鏄庣‘鎻愬嚭鐨勬柊鍋忓ソ锛歕n- pace.style: 鍋忚交鏉炬參鑺傚\n" + (
            "琛ュ厖璇存槑锛氬€惧悜灏戞崲閰掑簵銆佸皯鎶樿繑銆侀伩鍏嶈繃婊℃棩绋嬨€?" * 40
        )

        context = {
            "session_id": str(session.id),
            "session_summary": session.summary,
            "active_plan_option_id": str(uuid.uuid4()),
            "active_plan_title": "涓滀含鍛ㄦ湯涓绘柟妗?,
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
                    "title": "涓滀含鍛ㄦ湯涓绘柟妗?,
                    "status": "selected",
                    "primary_destination": "涓滀含",
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "绠辨牴澶囬€?,
                    "status": "draft",
                    "primary_destination": "绠辨牴",
                },
            ],
        }

        service = MemoryService(db=MagicMock())
        service.build_session_context_payload = MagicMock(return_value=context)

        messages = service.build_runtime_context_messages(
            session=session,
            current_user_input="缁х画淇濈暀鍛ㄦ湯杞绘澗鑺傚",
            recall_result={
                "summary": "鍛戒腑浜嗕笢浜懆鏈巻鍙茬煭閫旀柟妗堬紝鍙鐢ㄦ參鑺傚瀹夋帓銆?" * 30,
                "grouped_matches": {},
            },
            extra_sections=[
                duplicated_constraint,
                duplicated_constraint,
                "銆愭湰杞緭鍑鸿姹傘€慭n鍏堣ˉ姣忓ぉ瀹夋帓锛屽啀琛ラ厭搴楀缓璁€?" * 20,
            ],
        )

        system_message = messages[0]
        self.assertEqual(1, system_message.content.count("銆愭湰杞墽琛岀害鏉熴€?))
        self.assertLessEqual(len(system_message.content), RUNTIME_CONTEXT_TOTAL_MAX_LENGTH)
        self.assertIn("銆愬綋鍓嶆縺娲绘柟妗堣蹇嗐€?, system_message.content)
        self.assertIn("銆愭湰杞緭鍑鸿姹傘€?, system_message.content)


if __name__ == "__main__":
    unittest.main()
