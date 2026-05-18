"""OpenClaw MCP wrapper 背后的业务服务。"""

from __future__ import annotations

import os
import uuid

from services.channels.external_session_mapping_service import (
    ExternalSessionMappingService,
)
from services.chat.chat_turn_runner import ChatTurnRunner
from services.travel.trip_export_service import TripExportService
from services.travel.trip_service import TripService


def get_mcp_wrapper_channel() -> str:
    """读取当前 MCP wrapper 所属的渠道名。"""
    return (
        os.getenv("MCP_WRAPPER_CHANNEL", "wechat_openclaw").strip()
        or "wechat_openclaw"
    )


class OpenClawMcpService:
    """向 OpenClaw 暴露粗粒度旅行规划能力。"""

    def __init__(self, db):
        self.db = db
        self.mapping_service = ExternalSessionMappingService(db)
        self.chat_turn_runner = ChatTurnRunner(db)
        self.trip_service = TripService(db)
        self.trip_export_service = TripExportService()
        self.channel = get_mcp_wrapper_channel()

    def travel_chat(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        message: str,
    ) -> dict:
        """处理外部渠道发来的聊天请求。"""
        binding = self.mapping_service.resolve_or_create_binding(
            channel=self.channel,
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            first_message=message,
        )
        result = self.chat_turn_runner.run_turn(
            user=binding.user,
            message=message,
            session_id=binding.session.id,
        )
        workspace_payload = result.workspace_payload or {}
        return {
            "status": result.status,
            "degraded_reason": result.degraded_reason,
            "session_id": result.session_id,
            "reply": result.reply,
            "is_new_session": binding.is_new_session,
            "active_trip_id": workspace_payload.get("active_trip_id"),
            "active_trip_title": workspace_payload.get("active_trip_title"),
            "trip_ready": bool(workspace_payload.get("active_trip_id")),
        }

    def travel_get_active_trip(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
    ) -> dict:
        """查询当前外部会话绑定的 active trip。"""
        binding = self.mapping_service.get_binding_or_none(
            channel=self.channel,
            external_user_id=external_user_id,
            conversation_id=conversation_id,
        )
        if binding is None:
            return {
                "found": False,
                "message": "当前外部会话还没有绑定任何旅行规划会话。",
            }

        trip = self.trip_service.get_active_trip(
            session_id=binding.session.id,
            user_id=binding.user.id,
        )
        if trip is None:
            return {
                "found": False,
                "session_id": str(binding.session.id),
                "message": "当前会话还没有生成正式行程。",
                "trip_ready": False,
            }

        return {
            "found": True,
            "session_id": str(binding.session.id),
            "trip_id": str(trip.id),
            "title": trip.title,
            "summary": trip.summary,
            "primary_destination": trip.primary_destination,
            "total_days": trip.total_days,
            "trip_ready": True,
        }

    def travel_export_markdown(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        trip_id: str | None = None,
    ) -> dict:
        """导出当前会话或指定 trip 的 Markdown。"""
        binding = self.mapping_service.get_binding_or_none(
            channel=self.channel,
            external_user_id=external_user_id,
            conversation_id=conversation_id,
        )
        if binding is None:
            return {
                "found": False,
                "message": "当前外部会话还没有绑定任何旅行规划会话。",
            }

        if trip_id:
            trip = self.trip_service.get_trip_or_raise(
                session_id=binding.session.id,
                trip_id=uuid.UUID(trip_id),
                user_id=binding.user.id,
            )
        else:
            trip = self.trip_service.get_active_trip(
                session_id=binding.session.id,
                user_id=binding.user.id,
            )

        if trip is None:
            return {
                "found": False,
                "session_id": str(binding.session.id),
                "message": "当前会话还没有可导出的正式行程。",
            }

        markdown = self.trip_export_service.ensure_document_markdown(trip)
        filename = self.trip_export_service.build_markdown_filename(trip)
        return {
            "found": True,
            "session_id": str(binding.session.id),
            "trip_id": str(trip.id),
            "title": trip.title,
            "filename": filename,
            "markdown": markdown,
        }
