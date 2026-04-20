"""候选方案分支化规则。

这一层只负责“怎么命名 / 怎么识别分支根 / 怎么算分支层级”这类纯规则，
不直接处理数据库事务，也不关心 Web 或 HTTP。
"""

from __future__ import annotations

import uuid

from db.models import PlanOption


def build_plan_option_title(*, session_title: str | None, index: int) -> str:
    """根据会话标题生成默认方案标题。"""
    base = " ".join((session_title or "").split()).strip() or "旅行规划"
    return f"{base} - 方案 {index}"


def build_plan_branch_name(
    title: str | None,
    *,
    fallback_index: int | None = None,
) -> str:
    """生成适合持久化的分支名称。"""
    clean_title = " ".join((title or "").split()).strip()
    if clean_title:
        return clean_title[:120]
    if fallback_index is not None:
        return f"branch-{fallback_index}"
    return "main"


def build_forked_plan_option_title(*, source_title: str, branch_seq_no: int) -> str:
    """生成从已有方案复制出来的新分支标题。"""
    clean_title = " ".join((source_title or "").split()).strip() or "未命名方案"
    return f"{clean_title} - 分支 {branch_seq_no}"


def resolve_branch_root_option_id(plan_option: PlanOption) -> uuid.UUID:
    """解析方案所属分支树的根节点。"""
    if getattr(plan_option, "branch_root_option_id", None):
        return plan_option.branch_root_option_id
    if getattr(plan_option, "source_plan_option_id", None):
        return plan_option.source_plan_option_id
    return plan_option.id


def resolve_branch_root_and_depth(
    *,
    plan_option: PlanOption,
    item_map: dict[uuid.UUID, PlanOption],
) -> tuple[uuid.UUID, int]:
    """沿 parent/source 关系向上回溯，得到根分支和深度。"""
    current = plan_option
    depth = 0
    visited: set[uuid.UUID] = {plan_option.id}

    while current.parent_plan_option_id or current.source_plan_option_id:
        parent_id = current.parent_plan_option_id or current.source_plan_option_id
        if parent_id is None:
            break

        parent = item_map.get(parent_id)
        if parent is None or parent.id in visited:
            break

        current = parent
        visited.add(parent.id)
        depth += 1

    return current.branch_root_option_id or current.id, depth
