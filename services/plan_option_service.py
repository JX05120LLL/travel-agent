"""Plan option application service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import ChatSession, PlanOption, PlanOptionDestination
from db.repositories.message_repository import get_latest_assistant_message
from db.repositories.plan_option_repository import (
    add_plan_option,
    add_plan_option_destination,
    count_child_plan_options,
    count_session_plan_options,
    get_plan_option,
    list_plan_options,
)
from db.repositories.session_event_repository import create_session_event
from domain.plan_option.branching import (
    build_forked_plan_option_title,
    build_plan_branch_name,
    build_plan_option_title,
    resolve_branch_root_and_depth,
    resolve_branch_root_option_id,
)
from domain.plan_option.splitters import (
    build_plan_summary,
    extract_candidate_plan_blocks_with_city_fallback,
    extract_mentioned_destinations,
    guess_primary_destination,
    normalize_markdown_text,
)
from services.errors import ServiceNotFoundError
from services.memory_service import MemoryService
from services.session_management_service import SessionManagementService


@dataclass(slots=True)
class PlanOptionBranchView:
    """View model for a branched plan option."""

    plan_option: PlanOption
    branch_root_id: uuid.UUID
    branch_depth: int
    child_count: int


class PlanOptionService:
    """Application service for plan options."""

    def __init__(self, db: Session):
        self.db = db
        self.session_service = SessionManagementService(db)
        self.memory_service = MemoryService(db)

    def get_session_or_raise(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        session = self.session_service.get_session_or_raise(
            session_id=session_id,
            user_id=user_id,
        )
        return session

    def get_plan_option_or_raise(
        self,
        *,
        session: ChatSession,
        plan_option_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PlanOption:
        plan_option = get_plan_option(
            self.db,
            session_id=session.id,
            plan_option_id=plan_option_id,
            user_id=user_id,
        )
        if plan_option is None:
            raise ServiceNotFoundError("候选方案不存在")
        return plan_option

    def list_plan_option_views(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[ChatSession, list[PlanOptionBranchView]]:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        items = list_plan_options(self.db, session_id=session.id, user_id=user_id)
        return session, self._build_branch_views(items)

    def create_option(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
        primary_destination: str | None = None,
        travel_start_date=None,
        travel_end_date=None,
        total_days: int | None = None,
        summary: str | None = None,
        plan_markdown: str | None = None,
        activate: bool = True,
        commit: bool = True,
    ) -> PlanOptionBranchView:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        plan_option = self._create_plan_option(
            session=session,
            user_id=user_id,
            title=title,
            primary_destination=primary_destination,
            travel_start_date=travel_start_date,
            travel_end_date=travel_end_date,
            total_days=total_days,
            summary=summary,
            plan_markdown=plan_markdown,
            activate=activate,
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=[plan_option],
        )
        return self.build_branch_view(plan_option)

    def create_options_from_latest_message(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        commit: bool = True,
    ) -> list[PlanOptionBranchView]:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        latest_assistant = get_latest_assistant_message(self.db, session_id=session.id)
        if latest_assistant is None:
            raise ValueError("当前会话还没有可保存的助手回复。")

        existing_options = list_plan_options(self.db, session_id=session.id, user_id=user_id)
        existing_markdowns = {
            normalize_markdown_text(item.plan_markdown or "")
            for item in existing_options
            if item.plan_markdown
        }

        candidate_blocks = extract_candidate_plan_blocks_with_city_fallback(
            latest_assistant.content
        )
        if not candidate_blocks:
            candidate_blocks = [
                {
                    "title": None,
                    "summary": build_plan_summary(latest_assistant.content),
                    "plan_markdown": latest_assistant.content,
                    "primary_destination": guess_primary_destination(
                        latest_assistant.content
                    ),
                }
            ]

        created_items: list[PlanOption] = []
        for index, block in enumerate(candidate_blocks):
            normalized_block = normalize_markdown_text(block["plan_markdown"] or "")
            if normalized_block in existing_markdowns:
                continue

            plan_option = self._create_plan_option(
                session=session,
                user_id=user_id,
                title=block["title"],
                primary_destination=block["primary_destination"],
                summary=block["summary"],
                plan_markdown=block["plan_markdown"],
                activate=index == 0,
            )
            created_items.append(plan_option)
            existing_markdowns.add(normalized_block)

        if not created_items:
            raise ValueError("当前最新回复已经保存过候选方案了。")

        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=created_items,
        )
        return [self.build_branch_view(item) for item in created_items]

    def activate_option(
        self,
        *,
        session_id: uuid.UUID,
        plan_option_id: uuid.UUID,
        user_id: uuid.UUID,
        commit: bool = True,
    ) -> PlanOptionBranchView:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        plan_option = self.get_plan_option_or_raise(
            session=session,
            plan_option_id=plan_option_id,
            user_id=user_id,
        )
        self._activate_plan_option(session=session, plan_option=plan_option)
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=[plan_option],
        )
        return self.build_branch_view(plan_option)

    def fork_option(
        self,
        *,
        session_id: uuid.UUID,
        plan_option_id: uuid.UUID,
        user_id: uuid.UUID,
        activate: bool = True,
        commit: bool = True,
    ) -> PlanOptionBranchView:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        source_plan_option = self.get_plan_option_or_raise(
            session=session,
            plan_option_id=plan_option_id,
            user_id=user_id,
        )
        copied_option = self._copy_plan_option(
            session=session,
            source_plan_option=source_plan_option,
            activate=activate,
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=[copied_option],
        )
        return self.build_branch_view(copied_option)

    def archive_option(
        self,
        *,
        session_id: uuid.UUID,
        plan_option_id: uuid.UUID,
        user_id: uuid.UUID,
        commit: bool = True,
    ) -> PlanOptionBranchView:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        plan_option = self.get_plan_option_or_raise(
            session=session,
            plan_option_id=plan_option_id,
            user_id=user_id,
        )
        self._archive_or_delete_plan_option(
            session=session,
            plan_option=plan_option,
            target_status="archived",
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=[plan_option],
        )
        return self.build_branch_view(plan_option)

    def delete_option(
        self,
        *,
        session_id: uuid.UUID,
        plan_option_id: uuid.UUID,
        user_id: uuid.UUID,
        commit: bool = True,
    ) -> PlanOptionBranchView:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        plan_option = self.get_plan_option_or_raise(
            session=session,
            plan_option_id=plan_option_id,
            user_id=user_id,
        )
        self._archive_or_delete_plan_option(
            session=session,
            plan_option=plan_option,
            target_status="deleted",
        )
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=[plan_option],
        )
        return self.build_branch_view(plan_option)

    def expand_option_destinations(
        self,
        *,
        session_id: uuid.UUID,
        plan_option_id: uuid.UUID,
        user_id: uuid.UUID,
        destination_names: list[str],
        planning_mode: str | None = "multi_city",
        commit: bool = True,
    ) -> PlanOptionBranchView:
        session = self.get_session_or_raise(session_id=session_id, user_id=user_id)
        plan_option = self.get_plan_option_or_raise(
            session=session,
            plan_option_id=plan_option_id,
            user_id=user_id,
        )
        cleaned_names = self._ensure_plan_option_destinations(
            plan_option=plan_option,
            destination_names=destination_names,
        )
        if planning_mode and len(cleaned_names) > 1:
            plan_option.planning_mode = planning_mode
        session.updated_at = datetime.now()
        self.memory_service.refresh_session_memory(session=session, commit=False)
        self._commit_and_refresh(
            commit=commit,
            session=session,
            plan_options=[plan_option],
        )
        return self.build_branch_view(plan_option)

    def build_branch_view(self, plan_option: PlanOption) -> PlanOptionBranchView:
        items = list_plan_options(
            self.db,
            session_id=plan_option.session_id,
            user_id=plan_option.user_id,
        )
        item_map = {item.id: item for item in items}
        child_count_map = self._build_child_count_map(items)
        return self._to_branch_view(
            plan_option=plan_option,
            item_map=item_map,
            child_count_map=child_count_map,
        )

    def _create_plan_option(
        self,
        *,
        session: ChatSession,
        user_id: uuid.UUID,
        title: str | None = None,
        primary_destination: str | None = None,
        travel_start_date=None,
        travel_end_date=None,
        total_days: int | None = None,
        summary: str | None = None,
        plan_markdown: str | None = None,
        activate: bool = True,
    ) -> PlanOption:
        current_count = count_session_plan_options(self.db, session_id=session.id)
        resolved_title = (title or "").strip() or build_plan_option_title(
            session_title=session.title,
            index=current_count + 1,
        )
        resolved_branch_name = build_plan_branch_name(
            resolved_title,
            fallback_index=current_count + 1,
        )
        resolved_markdown = (plan_markdown or "").strip() or None
        resolved_summary = (summary or "").strip() or build_plan_summary(
            resolved_markdown or resolved_title
        )

        plan_option = add_plan_option(
            self.db,
            PlanOption(
                session_id=session.id,
                user_id=user_id,
                parent_plan_option_id=None,
                title=resolved_title[:200],
                branch_name=resolved_branch_name,
                status="active" if activate else "draft",
                primary_destination=(primary_destination or "").strip() or None,
                travel_start_date=travel_start_date,
                travel_end_date=travel_end_date,
                total_days=total_days,
                summary=resolved_summary or None,
                plan_markdown=resolved_markdown,
                is_selected=activate,
            ),
        )
        plan_option.branch_root_option_id = plan_option.id
        plan_option.source_plan_option_id = None

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=user_id,
            plan_option_id=plan_option.id,
            event_type="plan_option_created",
            event_payload={
                "title": plan_option.title,
                "branch_name": plan_option.branch_name,
                "branch_root_option_id": str(plan_option.branch_root_option_id),
                "primary_destination": plan_option.primary_destination,
                "activate": activate,
            },
        )

        self._ensure_plan_option_destinations(
            plan_option=plan_option,
            destination_names=extract_mentioned_destinations(
                plan_option.primary_destination,
                plan_option.title,
                plan_option.plan_markdown,
            ),
        )

        if activate:
            self._activate_plan_option(
                session=session,
                plan_option=plan_option,
                refresh_memory=False,
            )

        return plan_option

    def _copy_plan_option(
        self,
        *,
        session: ChatSession,
        source_plan_option: PlanOption,
        activate: bool = True,
    ) -> PlanOption:
        child_count = count_child_plan_options(
            self.db,
            parent_plan_option_id=source_plan_option.id,
        )
        branch_seq_no = child_count + 1
        copied_title = build_forked_plan_option_title(
            source_title=source_plan_option.title,
            branch_seq_no=branch_seq_no,
        )

        copied_option = add_plan_option(
            self.db,
            PlanOption(
                session_id=session.id,
                user_id=source_plan_option.user_id,
                parent_plan_option_id=source_plan_option.id,
                branch_root_option_id=resolve_branch_root_option_id(source_plan_option),
                source_plan_option_id=source_plan_option.id,
                branch_name=build_plan_branch_name(
                    copied_title,
                    fallback_index=branch_seq_no,
                ),
                title=copied_title[:200],
                status="active" if activate else "draft",
                planning_mode=source_plan_option.planning_mode,
                primary_destination=source_plan_option.primary_destination,
                travel_start_date=source_plan_option.travel_start_date,
                travel_end_date=source_plan_option.travel_end_date,
                total_days=source_plan_option.total_days,
                traveler_profile=dict(source_plan_option.traveler_profile or {}),
                budget_min=source_plan_option.budget_min,
                budget_max=source_plan_option.budget_max,
                pace=source_plan_option.pace,
                preferences=dict(source_plan_option.preferences or {}),
                constraints=dict(source_plan_option.constraints or {}),
                summary=source_plan_option.summary,
                plan_markdown=source_plan_option.plan_markdown,
                version_no=source_plan_option.version_no + 1,
                is_selected=activate,
            ),
        )

        for destination in source_plan_option.destinations:
            add_plan_option_destination(
                self.db,
                PlanOptionDestination(
                    plan_option_id=copied_option.id,
                    sequence_no=destination.sequence_no,
                    destination_name=destination.destination_name,
                    destination_code=destination.destination_code,
                    stay_days=destination.stay_days,
                    notes=destination.notes,
                ),
            )

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=source_plan_option.user_id,
            plan_option_id=copied_option.id,
            event_type="plan_option_copied",
            event_payload={
                "source_plan_option_id": str(source_plan_option.id),
                "parent_plan_option_id": str(source_plan_option.id),
                "branch_root_option_id": str(copied_option.branch_root_option_id),
                "branch_name": copied_option.branch_name,
                "title": copied_option.title,
                "version_no": copied_option.version_no,
            },
        )

        if activate:
            self._activate_plan_option(
                session=session,
                plan_option=copied_option,
                refresh_memory=False,
            )

        return copied_option

    def _activate_plan_option(
        self,
        *,
        session: ChatSession,
        plan_option: PlanOption,
        refresh_memory: bool = True,
    ) -> PlanOption:
        options = list_plan_options(
            self.db,
            session_id=session.id,
            user_id=plan_option.user_id,
        )
        for item in options:
            item.is_selected = item.id == plan_option.id
            if item.id != plan_option.id and item.status == "selected":
                item.status = "active"

        plan_option.is_selected = True
        plan_option.status = "selected"
        session.active_plan_option_id = plan_option.id
        session.updated_at = datetime.now()

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=plan_option.user_id,
            plan_option_id=plan_option.id,
            event_type="plan_option_activated",
            event_payload={
                "title": plan_option.title,
                "primary_destination": plan_option.primary_destination,
            },
        )

        if refresh_memory:
            self.memory_service.refresh_session_memory(session=session, commit=False)

        return plan_option

    def _archive_or_delete_plan_option(
        self,
        *,
        session: ChatSession,
        plan_option: PlanOption,
        target_status: str,
    ) -> PlanOption:
        replacement = None
        if session.active_plan_option_id == plan_option.id:
            replacement = self._pick_next_active_plan_option(
                session=session,
                excluding_plan_option_id=plan_option.id,
            )

        plan_option.status = target_status
        plan_option.is_selected = False
        plan_option.archived_at = datetime.now()
        session.updated_at = datetime.now()

        if replacement is not None:
            self._activate_plan_option(
                session=session,
                plan_option=replacement,
                refresh_memory=False,
            )
        elif session.active_plan_option_id == plan_option.id:
            session.active_plan_option_id = None

        create_session_event(
            self.db,
            session_id=session.id,
            user_id=plan_option.user_id,
            plan_option_id=plan_option.id,
            event_type=(
                "plan_option_archived"
                if target_status == "archived"
                else "plan_option_deleted"
            ),
            event_payload={"title": plan_option.title},
        )
        return plan_option

    def _pick_next_active_plan_option(
        self,
        *,
        session: ChatSession,
        excluding_plan_option_id: uuid.UUID,
    ) -> PlanOption | None:
        candidates = [
            item
            for item in list_plan_options(
                self.db,
                session_id=session.id,
                user_id=session.user_id,
            )
            if item.id != excluding_plan_option_id
            and item.status not in ("archived", "deleted")
        ]
        return candidates[0] if candidates else None

    def _ensure_plan_option_destinations(
        self,
        *,
        plan_option: PlanOption,
        destination_names: list[str],
    ) -> list[str]:
        cleaned_names: list[str] = []
        seen: set[str] = set()
        for name in destination_names:
            clean_name = (name or "").strip()
            if clean_name and clean_name not in seen:
                cleaned_names.append(clean_name)
                seen.add(clean_name)

        if not cleaned_names:
            return []

        existing_items = list(plan_option.destinations)
        existing_names = {item.destination_name for item in existing_items}

        if len(cleaned_names) > 1:
            plan_option.planning_mode = "multi_city"

        for name in cleaned_names:
            if name in existing_names:
                continue

            destination = add_plan_option_destination(
                self.db,
                PlanOptionDestination(
                    plan_option_id=plan_option.id,
                    sequence_no=len(existing_items) + 1,
                    destination_name=name,
                    notes="自动从会话需求中识别",
                ),
            )
            existing_items.append(destination)
            existing_names.add(name)

        return cleaned_names

    def _commit_and_refresh(
        self,
        *,
        commit: bool,
        session: ChatSession | None = None,
        plan_options: list[PlanOption] | None = None,
    ) -> None:
        if not commit:
            return

        self.db.commit()
        if session is not None:
            self.db.refresh(session)
        for item in plan_options or []:
            self.db.refresh(item)

    def _build_branch_views(
        self,
        items: list[PlanOption],
    ) -> list[PlanOptionBranchView]:
        item_map = {item.id: item for item in items}
        child_count_map = self._build_child_count_map(items)
        return [
            self._to_branch_view(
                plan_option=item,
                item_map=item_map,
                child_count_map=child_count_map,
            )
            for item in items
        ]

    @staticmethod
    def _build_child_count_map(items: list[PlanOption]) -> dict[uuid.UUID, int]:
        child_count_map: dict[uuid.UUID, int] = {}
        for item in items:
            parent_id = item.parent_plan_option_id or item.source_plan_option_id
            if parent_id is None:
                continue
            child_count_map[parent_id] = child_count_map.get(parent_id, 0) + 1
        return child_count_map

    def _to_branch_view(
        self,
        *,
        plan_option: PlanOption,
        item_map: dict[uuid.UUID, PlanOption],
        child_count_map: dict[uuid.UUID, int],
    ) -> PlanOptionBranchView:
        branch_root_id, branch_depth = resolve_branch_root_and_depth(
            plan_option=plan_option,
            item_map=item_map,
        )
        return PlanOptionBranchView(
            plan_option=plan_option,
            branch_root_id=branch_root_id,
            branch_depth=branch_depth,
            child_count=child_count_map.get(plan_option.id, 0),
        )
