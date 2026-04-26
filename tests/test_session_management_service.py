import sys
import types
import unittest
import uuid
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
from services.session_management_service import SessionManagementService


class SessionManagementServiceTests(unittest.TestCase):
    @patch("services.session_management_service.create_session_event")
    def test_set_session_pinned_updates_state_and_payload(self, create_session_event):
        db = MagicMock()
        service = SessionManagementService(db)
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="杭州周末",
            status="active",
        )

        result = service.set_session_pinned(
            session=session,
            is_pinned=True,
            commit=False,
        )

        self.assertTrue(result.is_pinned)
        self.assertIsNotNone(result.pinned_at)
        create_session_event.assert_called_once()
        self.assertEqual(
            True,
            create_session_event.call_args.kwargs["event_payload"]["is_pinned"],
        )

    @patch("services.session_management_service.create_session_event")
    def test_set_session_pinned_can_clear_state(self, create_session_event):
        db = MagicMock()
        service = SessionManagementService(db)
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="北京出差",
            status="active",
            is_pinned=True,
        )

        result = service.set_session_pinned(
            session=session,
            is_pinned=False,
            commit=False,
        )

        self.assertFalse(result.is_pinned)
        self.assertIsNone(result.pinned_at)
        self.assertEqual(
            False,
            create_session_event.call_args.kwargs["event_payload"]["is_pinned"],
        )


if __name__ == "__main__":
    unittest.main()
