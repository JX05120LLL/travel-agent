import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.message_service import MessageService


class MessageServiceTests(unittest.TestCase):
    @patch("services.message_service.create_session_event")
    @patch("services.message_service.add_message")
    def test_save_user_message_respects_commit_false(
        self,
        add_message,
        create_session_event,
    ):
        db = MagicMock()
        service = MessageService(db)
        service.memory_service = MagicMock()
        service.preference_service = MagicMock()
        service.preference_service.remember_from_message.return_value = []

        session = SimpleNamespace(
            id=uuid.uuid4(),
            active_plan_option_id=None,
            updated_at=None,
            last_message_at=None,
            latest_user_message=None,
        )
        saved_message = SimpleNamespace(id=uuid.uuid4())
        add_message.return_value = saved_message

        result = service.save_user_message(
            session=session,
            user_id=uuid.uuid4(),
            content="帮我规划杭州两天旅行",
            commit=False,
        )

        self.assertIs(result, saved_message)
        self.assertFalse(db.commit.called)
        self.assertFalse(db.refresh.called)
        service.memory_service.refresh_session_memory.assert_called_once_with(
            session=session,
            commit=False,
        )
        create_session_event.assert_called_once()

    @patch("services.message_service.create_session_event")
    @patch("services.message_service.add_message")
    def test_save_assistant_message_merges_metadata_and_respects_commit_false(
        self,
        add_message,
        create_session_event,
    ):
        db = MagicMock()
        service = MessageService(db)
        service.memory_service = MagicMock()

        session = SimpleNamespace(
            id=uuid.uuid4(),
            active_plan_option_id=None,
            updated_at=None,
            last_message_at=None,
        )
        saved_message = SimpleNamespace(id=uuid.uuid4())
        add_message.return_value = saved_message

        result = service.save_assistant_message(
            session=session,
            user_id=uuid.uuid4(),
            content="这是推荐方案",
            tool_outputs=["tool output"],
            has_error=False,
            extra_metadata={"workspace_sync": {"auto_synced_trip": True}},
            commit=False,
        )

        self.assertIs(result, saved_message)
        self.assertFalse(db.commit.called)
        self.assertFalse(db.refresh.called)
        _, kwargs = add_message.call_args
        self.assertEqual(
            {
                "tool_outputs": ["tool output"],
                "has_error": False,
                "workspace_sync": {"auto_synced_trip": True},
            },
            kwargs["metadata"],
        )
        service.memory_service.refresh_session_memory.assert_called_once_with(
            session=session,
            commit=False,
        )
        create_session_event.assert_called_once()


if __name__ == "__main__":
    unittest.main()
