"""12306 跨城到达规划工具。"""

from __future__ import annotations

from langchain_core.tools import tool

from services.train_12306_service import (
    JisuApiTrainProvider,
    MCP12306Provider,
    RailTripQuery,
    TuniuFreeApiProvider,
    get_train_12306_service,
)


def _render_arrival_payload(payload: dict) -> str:
    official_notice = payload.get("official_notice") or {}
    provider_status = payload.get("provider_status") or {}
    candidates = payload.get("candidates") or []

    lines = [
        "## 跨城到达建议（12306）",
        f"- 出发城市：{payload.get('origin_city') or '待补充'}",
        f"- 目的城市：{payload.get('destination_city') or '待补充'}",
        f"- 出发日期：{payload.get('depart_date') or '待补充'}",
        f"- 推荐方式：{payload.get('recommended_mode') or '待补充'}",
        f"- 预计耗时：{payload.get('duration_text') or '待补充'}",
        f"- 票价参考：{payload.get('price_text') or '待补充'}",
        f"- 接入状态：{payload.get('booking_status') or 'unknown'}",
        f"- 票务状态：{payload.get('ticket_status') or 'reference'}",
        f"- 数据来源：{payload.get('data_source') or payload.get('provider') or 'unknown'}",
        f"- 数据时效：{payload.get('fetched_at') or '待补充'}",
        f"- 方案摘要：{payload.get('summary') or '已生成到达建议'}",
    ]
    if payload.get("degraded_reason"):
        lines.append(f"- 降级原因：{payload.get('degraded_reason')}")
    if provider_status:
        lines.append(f"- 命中来源：{provider_status.get('selected_provider') or '未知'}")
        fallback_errors = provider_status.get("fallback_errors") or []
        if fallback_errors:
            lines.append(f"- 降级记录：{'；'.join(str(item) for item in fallback_errors[:3])}")

    if candidates:
        lines.extend(["", "### 推荐车次"])
        for index, item in enumerate(candidates[:3], start=1):
            train_no = item.get("train_no") or "待补充车次"
            stations = " -> ".join(
                [
                    str(value).strip()
                    for value in [item.get("depart_station"), item.get("arrive_station")]
                    if str(value or "").strip()
                ]
            )
            meta_parts = [
                item.get("depart_time"),
                item.get("arrive_time"),
                item.get("duration_text"),
                item.get("price_text"),
                item.get("availability_text"),
            ]
            lines.append(f"{index}. {train_no}")
            if stations:
                lines.append(f"   - 站点：{stations}")
            if any(meta_parts):
                lines.append(
                    "   - 信息："
                    + " / ".join(str(part) for part in meta_parts if str(part or "").strip())
                )

    lines.extend(
        [
            "",
            "### 官方购票提醒",
            f"- 渠道：{official_notice.get('channel_name') or '铁路12306官方'}",
            f"- 官网：{official_notice.get('website_url') or 'https://www.12306.cn/'}",
            f"- App：{official_notice.get('app_url') or 'https://kyfw.12306.cn/otn/appDownload/init'}",
            f"- 提醒：{official_notice.get('notice') or '车次、票价与余票请以官方为准。'}",
            "",
            "### 补充说明",
        ]
    )

    notes = payload.get("notes") or []
    if not notes:
        notes = ["当前未获取到更完整的车次信息。"]
    if payload.get("provider_mode") == "placeholder" or not candidates:
        notes = [
            "暂未获取到真实车次；请不要把下方占位建议当作具体车次。",
            *notes,
        ]
    lines.extend(f"- {note}" for note in notes if note)
    return "\n".join(lines)


@tool
def plan_12306_arrival(
    origin_city: str,
    destination_city: str,
    depart_date: str = "",
) -> str:
    """铁路/12306 跨城到达建议。"""
    try:
        payload = get_train_12306_service().plan_arrival(
            origin_city=origin_city,
            destination_city=destination_city,
            depart_date=depart_date,
        )
    except ValueError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - 工具兜底
        return f"12306 到达规划失败：{exc}"
    return _render_arrival_payload(payload)


@tool
def query_train_tickets_mcp_12306(
    origin_city: str,
    destination_city: str,
    depart_date: str,
) -> str:
    """直接查询 12306 MCP provider，便于本地联调和验收。"""
    try:
        payload = MCP12306Provider().search_trips(
            RailTripQuery(
                origin_city=(origin_city or "").strip(),
                destination_city=(destination_city or "").strip(),
                depart_date=(depart_date or "").strip(),
            )
        ).to_dict()
        return _render_arrival_payload(payload)
    except Exception as exc:  # pragma: no cover - 调试工具兜底
        return f"12306 MCP 查询失败：{exc}"


@tool
def query_train_tickets_free_api(
    origin_city: str,
    destination_city: str,
    depart_date: str,
) -> str:
    """直接查询第三方火车票 free-api provider，便于实验性 smoke。"""
    try:
        payload = TuniuFreeApiProvider().search_trips(
            RailTripQuery(
                origin_city=(origin_city or "").strip(),
                destination_city=(destination_city or "").strip(),
                depart_date=(depart_date or "").strip(),
            )
        ).to_dict()
        return _render_arrival_payload(payload)
    except Exception as exc:  # pragma: no cover - 调试工具兜底
        return f"第三方火车票查询失败：{exc}"


@tool
def query_train_tickets_jisu_api(
    origin_city: str,
    destination_city: str,
    depart_date: str,
) -> str:
    """直接查询 Jisu/极速数据火车票 provider，便于单独 smoke。"""
    try:
        payload = JisuApiTrainProvider().search_trips(
            RailTripQuery(
                origin_city=(origin_city or "").strip(),
                destination_city=(destination_city or "").strip(),
                depart_date=(depart_date or "").strip(),
            )
        ).to_dict()
        return _render_arrival_payload(payload)
    except Exception as exc:  # pragma: no cover - 调试工具兜底
        return f"Jisu 火车票查询失败：{exc}"
