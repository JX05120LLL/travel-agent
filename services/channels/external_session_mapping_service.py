"""外部渠道身份与会话映射服务。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from db.models import ChatSession, User
from db.models.external_conversation import ExternalConversation
from db.models.external_identity import ExternalIdentity
from db.repositories.external_conversation_repository import (
    add_external_conversation,
    get_external_conversation,
)
from db.repositories.external_identity_repository import (
    add_external_identity,
    get_external_identity,
)
from db.repositories.user_repository import add_user
from services.core.errors import ServiceNotFoundError
from services.session.session_management_service import SessionManagementService


@dataclass(slots=True)
class ExternalSessionBinding:
    """一次外部会话绑定解析后的统一结果。"""

    user: User
    session: ChatSession
    conversation: ExternalConversation
    identity: ExternalIdentity
    is_new_session: bool


class ExternalSessionMappingService:
    """把外部 user/conversation 映射为内部 user/session。"""

    def __init__(self, db):
        self.db = db
        self.session_management_service = SessionManagementService(db)

    def resolve_or_create_binding(
        self,
        *,
        channel: str,
        external_user_id: str,
        conversation_id: str,
        first_message: str = "",
        profile_json: dict | None = None,
        metadata_json: dict | None = None,
    ) -> ExternalSessionBinding:
        """查找或创建一条完整的外部会话绑定。"""
        normalized_channel = (channel or "").strip() or "external"
        normalized_external_user_id = (external_user_id or "").strip()
        normalized_conversation_id = (conversation_id or "").strip()
        if not normalized_external_user_id:
            raise ValueError("external_user_id 不能为空")
        if not normalized_conversation_id:
            raise ValueError("conversation_id 不能为空")

        identity = get_external_identity(
            self.db,
            channel=normalized_channel,
            external_user_id=normalized_external_user_id,
        )
        if identity is None:
            user = self._create_external_user(
                channel=normalized_channel,
                external_user_id=normalized_external_user_id,
            )
            identity = add_external_identity(
                self.db,
                ExternalIdentity(
                    channel=normalized_channel,
                    external_user_id=normalized_external_user_id,
                    user_id=user.id,
                    profile_json=dict(profile_json or {}),
                ),
            )
        else:
            user = identity.user
            if profile_json:
                merged_profile = dict(identity.profile_json or {})
                merged_profile.update(profile_json)
                identity.profile_json = merged_profile

        conversation = get_external_conversation(
            self.db,
            channel=normalized_channel,
            external_user_id=normalized_external_user_id,
            conversation_id=normalized_conversation_id,
        )
        is_new_session = False
        if conversation is None:
            session = self.session_management_service.create_session(
                user_id=user.id,
                first_message=first_message,
                commit=False,
            )
            conversation = add_external_conversation(
                self.db,
                ExternalConversation(
                    channel=normalized_channel,
                    external_user_id=normalized_external_user_id,
                    conversation_id=normalized_conversation_id,
                    user_id=user.id,
                    session_id=session.id,
                    metadata_json=dict(metadata_json or {}),
                    last_message_at=datetime.now(),
                ),
            )
            is_new_session = True
        else:
            session = self._resolve_existing_session(conversation=conversation, user=user)
            if metadata_json:
                merged_metadata = dict(conversation.metadata_json or {})
                merged_metadata.update(metadata_json)
                conversation.metadata_json = merged_metadata
            conversation.last_message_at = datetime.now()
            conversation.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(user)
        self.db.refresh(conversation)
        self.db.refresh(session)
        return ExternalSessionBinding(
            user=user,
            session=session,
            conversation=conversation,
            identity=identity,
            is_new_session=is_new_session,
        )

    def get_binding_or_none(
        self,
        *,
        channel: str,
        external_user_id: str,
        conversation_id: str,
    ) -> ExternalSessionBinding | None:
        """只查询现有绑定，不自动创建。"""
        conversation = get_external_conversation(
            self.db,
            channel=channel,
            external_user_id=external_user_id,
            conversation_id=conversation_id,
        )
        if conversation is None:
            return None
        user = conversation.user
        identity = get_external_identity(
            self.db,
            channel=channel,
            external_user_id=external_user_id,
        )
        if identity is None:
            return None
        session = self._resolve_existing_session(conversation=conversation, user=user)
        return ExternalSessionBinding(
            user=user,
            session=session,
            conversation=conversation,
            identity=identity,
            is_new_session=False,
        )

    def _resolve_existing_session(
        self,
        *,
        conversation: ExternalConversation,
        user: User,
    ) -> ChatSession:
        """确保映射到的内部 session 仍然有效。"""
        try:
            return self.session_management_service.get_session_or_raise(
                session_id=conversation.session_id,
                user_id=user.id,
            )
        except ServiceNotFoundError:
            session = self.session_management_service.create_session(
                user_id=user.id,
                first_message="",
                commit=False,
            )
            conversation.session_id = session.id
            conversation.user_id = user.id
            conversation.last_message_at = datetime.now()
            return session

    def _create_external_user(self, *, channel: str, external_user_id: str) -> User:
        """为外部渠道自动创建一个内部用户。"""
        digest = hashlib.sha256(
            f"{channel}:{external_user_id}".encode("utf-8")
        ).hexdigest()[:20]
        username_prefix = channel.replace("-", "_").replace(" ", "_")[:12] or "external"
        username = f"{username_prefix}_{digest}"[:50]
        user = User(
            username=username,
            email=None,
            password_hash="external_auth_not_for_login",
            display_name=f"{channel}:{external_user_id}"[:100],
            status="active",
        )
        add_user(self.db, user)
        return user
