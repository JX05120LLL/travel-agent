import sys
import types
import unittest
import uuid
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

from db.models import User
from services.channels.external_session_mapping_service import (
    ExternalSessionMappingService,
)


class ExternalSessionMappingServiceTests(unittest.TestCase):
    @patch("services.channels.external_session_mapping_service.add_external_conversation")
    @patch("services.channels.external_session_mapping_service.add_external_identity")
    @patch("services.channels.external_session_mapping_service.add_user")
    @patch("services.channels.external_session_mapping_service.get_external_conversation")
    @patch("services.channels.external_session_mapping_service.get_external_identity")
    def test_first_binding_creates_identity_conversation_and_session(
        self,
        get_external_identity,
        get_external_conversation,
        add_user,
        add_external_identity,
        add_external_conversation,
    ):
        db = MagicMock()
        service = ExternalSessionMappingService(db)
        created_user = User(
            id=uuid.uuid4(),
            username="wechat_oc_test",
            email=None,
            password_hash="x",
            display_name="wx user",
            status="active",
        )
        add_user.side_effect = (
            lambda _db, user: setattr(user, "id", created_user.id) or user
        )
        get_external_identity.return_value = None
        get_external_conversation.return_value = None
        add_external_identity.side_effect = (
            lambda _db, item: setattr(item, "id", uuid.uuid4()) or item
        )
        add_external_conversation.side_effect = (
            lambda _db, item: setattr(item, "id", uuid.uuid4()) or item
        )
        created_session = SimpleNamespace(id=uuid.uuid4(), user_id=created_user.id)
        service.session_management_service = MagicMock()
        service.session_management_service.create_session.return_value = created_session

        result = service.resolve_or_create_binding(
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            conversation_id="conv_1",
            first_message="帮我规划杭州三天",
        )

        self.assertTrue(result.is_new_session)
        self.assertEqual(created_session.id, result.session.id)
        service.session_management_service.create_session.assert_called_once_with(
            user_id=created_user.id,
            first_message="帮我规划杭州三天",
            commit=False,
        )
        db.commit.assert_called_once()

    @patch("services.channels.external_session_mapping_service.get_external_conversation")
    @patch("services.channels.external_session_mapping_service.get_external_identity")
    def test_existing_binding_reuses_existing_session(
        self,
        get_external_identity,
        get_external_conversation,
    ):
        db = MagicMock()
        service = ExternalSessionMappingService(db)
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        user = User(
            id=user_id,
            username="wechat_oc_existing",
            email=None,
            password_hash="x",
            display_name="wx user",
            status="active",
        )
        identity = SimpleNamespace(
            id=uuid.uuid4(),
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            user=user,
            user_id=user.id,
            profile_json={},
        )
        conversation = SimpleNamespace(
            id=uuid.uuid4(),
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            conversation_id="conv_1",
            user=user,
            user_id=user.id,
            session_id=session_id,
            metadata_json={},
            last_message_at=None,
            updated_at=None,
        )
        get_external_identity.return_value = identity
        get_external_conversation.return_value = conversation
        service.session_management_service = MagicMock()
        service.session_management_service.get_session_or_raise.return_value = (
            SimpleNamespace(
                id=session_id,
                user_id=user.id,
            )
        )

        result = service.resolve_or_create_binding(
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            conversation_id="conv_1",
            first_message="继续刚才的行程",
        )

        self.assertFalse(result.is_new_session)
        self.assertEqual(session_id, result.session.id)
        service.session_management_service.get_session_or_raise.assert_called_once()

    @patch("services.channels.external_session_mapping_service.get_external_conversation")
    @patch("services.channels.external_session_mapping_service.get_external_identity")
    def test_same_user_different_conversation_can_resolve_different_sessions(
        self,
        get_external_identity,
        get_external_conversation,
    ):
        db = MagicMock()
        service = ExternalSessionMappingService(db)
        user = User(
            id=uuid.uuid4(),
            username="wechat_oc_existing",
            email=None,
            password_hash="x",
            display_name="wx user",
            status="active",
        )
        identity = SimpleNamespace(
            id=uuid.uuid4(),
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            user=user,
            user_id=user.id,
            profile_json={},
        )
        get_external_identity.return_value = identity
        get_external_conversation.side_effect = [
            SimpleNamespace(
                id=uuid.uuid4(),
                channel="wechat_openclaw",
                external_user_id="wx_u_1",
                conversation_id="conv_1",
                user=user,
                user_id=user.id,
                session_id=uuid.uuid4(),
                metadata_json={},
                last_message_at=None,
                updated_at=None,
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                channel="wechat_openclaw",
                external_user_id="wx_u_1",
                conversation_id="conv_2",
                user=user,
                user_id=user.id,
                session_id=uuid.uuid4(),
                metadata_json={},
                last_message_at=None,
                updated_at=None,
            ),
        ]
        first_session = SimpleNamespace(id=uuid.uuid4(), user_id=user.id)
        second_session = SimpleNamespace(id=uuid.uuid4(), user_id=user.id)
        service.session_management_service = MagicMock()
        service.session_management_service.get_session_or_raise.side_effect = [
            first_session,
            second_session,
        ]

        first = service.resolve_or_create_binding(
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            conversation_id="conv_1",
        )
        second = service.resolve_or_create_binding(
            channel="wechat_openclaw",
            external_user_id="wx_u_1",
            conversation_id="conv_2",
        )

        self.assertNotEqual(first.session.id, second.session.id)
