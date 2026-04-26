import unittest
import uuid
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "langchain_core.messages" not in sys.modules:
    langchain_core = types.ModuleType("langchain_core")
    messages_module = types.ModuleType("langchain_core.messages")

    class _Message:
        def __init__(self, content=None):
            self.content = content

    messages_module.AIMessage = _Message
    messages_module.HumanMessage = _Message
    messages_module.SystemMessage = _Message
    langchain_core.messages = messages_module
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.messages"] = messages_module

from db.models import ChatSession
from services.checkpoint_service import CheckpointService


def build_session() -> ChatSession:
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="测试工作区",
        status="active",
    )
    session.summary = "当前会话摘要"
    session.active_plan_option_id = uuid.uuid4()
    session.active_comparison_id = uuid.uuid4()
    return session


class CheckpointServiceTests(unittest.TestCase):
    @patch("services.checkpoint_service.create_session_event")
    @patch("services.checkpoint_service.list_plan_options")
    def test_create_checkpoint_contains_explicit_snapshot_scope(
        self,
        list_plan_options,
        create_session_event,
    ):
        session = build_session()
        list_plan_options.return_value = [
            SimpleNamespace(
                id=session.active_plan_option_id,
                title="北京方案",
                status="selected",
                is_selected=True,
                primary_destination="北京",
                total_days=3,
                summary="北京三天方案",
                plan_markdown="北京三天方案详情",
                version_no=1,
                branch_name="main",
                parent_plan_option_id=None,
                branch_root_option_id=session.active_plan_option_id,
                source_plan_option_id=None,
            )
        ]
        create_session_event.side_effect = (
            lambda db, **kwargs: SimpleNamespace(
                id=uuid.uuid4(),
                event_payload=kwargs["event_payload"],
            )
        )

        service = CheckpointService(db=MagicMock())
        checkpoint = service.create_checkpoint(
            session=session,
            label="比较前快照",
            commit=False,
        )

        payload = checkpoint.event_payload
        self.assertEqual("比较前快照", payload["label"])
        self.assertEqual(1, payload["captured_plan_option_count"])
        self.assertEqual(
            "restore_seed_then_refresh_from_messages",
            payload["summary_restore_mode"],
        )
        self.assertTrue(payload["snapshot_scope"]["restores_plan_options"])
        self.assertTrue(payload["snapshot_scope"]["does_not_restore_messages"])
        self.assertTrue(payload["snapshot_scope"]["does_not_restore_trip_rows"])

    @patch("services.checkpoint_service.create_session_event")
    @patch("services.checkpoint_service.list_plan_options")
    def test_rewind_checkpoint_emits_restore_metadata(
        self,
        list_plan_options,
        create_session_event,
    ):
        session = build_session()
        current_option = SimpleNamespace(
            id=session.active_plan_option_id,
            parent_plan_option_id=None,
            branch_root_option_id=None,
            source_plan_option_id=None,
            branch_name=None,
            title="旧标题",
            status="draft",
            primary_destination=None,
            total_days=None,
            summary=None,
            plan_markdown=None,
            version_no=1,
            is_selected=False,
            archived_at=None,
        )
        list_plan_options.return_value = [current_option]
        create_session_event.side_effect = (
            lambda db, **kwargs: SimpleNamespace(
                id=uuid.uuid4(),
                event_payload=kwargs["event_payload"],
            )
        )

        checkpoint = SimpleNamespace(
            id=uuid.uuid4(),
            event_payload={
                "label": "回滚点",
                "session_summary": "回滚前摘要",
                "active_plan_option_id": str(session.active_plan_option_id),
                "active_comparison_id": str(session.active_comparison_id),
                "summary_restore_mode": "restore_seed_then_refresh_from_messages",
                "snapshot_scope": {
                    "restores_plan_options": True,
                    "does_not_restore_messages": True,
                },
                "plan_snapshots": [
                    {
                        "id": str(session.active_plan_option_id),
                        "title": "回滚后的方案",
                        "status": "selected",
                        "is_selected": True,
                        "primary_destination": "上海",
                        "total_days": 2,
                        "summary": "上海周末方案",
                        "plan_markdown": "上海周末方案详情",
                        "version_no": 2,
                        "branch_name": "main",
                        "parent_plan_option_id": None,
                        "branch_root_option_id": str(session.active_plan_option_id),
                        "source_plan_option_id": None,
                    }
                ],
            },
        )

        service = CheckpointService(db=MagicMock())
        service.memory_service = MagicMock()

        restored_session = service.rewind_to_checkpoint(
            session=session,
            checkpoint=checkpoint,
            commit=False,
        )

        rewind_payload = create_session_event.call_args_list[-1].kwargs["event_payload"]
        self.assertEqual(str(checkpoint.id), rewind_payload["checkpoint_id"])
        self.assertEqual(1, rewind_payload["restored_plan_option_count"])
        self.assertTrue(rewind_payload["summary_refresh_applied"])
        self.assertTrue(rewind_payload["snapshot_scope"]["does_not_restore_messages"])
        self.assertEqual(
            "restore_seed_then_refresh_from_messages",
            rewind_payload["summary_restore_mode"],
        )
        self.assertEqual("回滚后的方案", current_option.title)
        self.assertEqual(restored_session.active_plan_option_id, session.active_plan_option_id)
        service.memory_service.refresh_session_memory.assert_called_once_with(
            session=session,
            commit=False,
        )


if __name__ == "__main__":
    unittest.main()
