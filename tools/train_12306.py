"""12306 跨城到达规划工具。"""

from __future__ import annotations

from langchain_core.tools import tool

from services.providers.train_12306_service import (
    JisuApiTrainProvider,
    MCP12306Provider,
    RailTripQuery,
    TuniuFreeApiProvider,
    get_train_12306_service,
)


def _is_high_speed_train(train_no: str | None) -> bool:
    return str(train_no or "").strip().upper().startswith(("G", "D", "C"))


def _prefer_high_speed_payload(payload: dict) -> dict:
    """Move high-speed candidates to the front for explicit high-speed queries."""
    candidates = list(payload.get("candidates") or [])
    high_speed = [
        item for item in candidates if _is_high_speed_train(item.get("train_no"))
    ]
    if not high_speed:
        return payload

    regular = [
        item for item in candidates if not _is_high_speed_train(item.get("train_no"))
    ]
    preferred = high_speed + regular
    best = preferred[0]
    payload = dict(payload)
    payload["candidates"] = preferred
    payload["recommended_mode"] = "高铁/动车"
    payload["duration_text"] = best.get("duration_text") or payload.get("duration_text")
    payload["price_text"] = best.get("price_text") or payload.get("price_text")
    payload["summary"] = (
        f"建议优先选择 {best.get('train_no') or '高铁/动车'}，"
        f"从 {best.get('depart_station') or payload.get('origin_city') or '出发地'} "
        f"到 {best.get('arrive_station') or payload.get('destination_city') or '目的地'}。"
    )
    return payload


def _render_transfer_payload(payload: dict, *, origin_city: str, destination_city: str, depart_date: str) -> str:
    transfers = list(payload.get("transfers") or [])
    lines = [
        "## 中转换乘建议（12306）",
        f"- 出发城市：{origin_city or payload.get('from_station') or '未提供'}",
        f"- 目的城市：{destination_city or payload.get('to_station') or '未提供'}",
        f"- 出发日期：{depart_date or payload.get('train_date') or '未提供'}",
        f"- 数据来源：mcp12306",
        f"- 中转方案数：{payload.get('count', len(transfers))}",
    ]

    if transfers:
        lines.extend(["", "### 推荐中转方案"])
        for index, item in enumerate(transfers[:3], start=1):
            lines.append(f"{index}. 经 {item.get('middle_station') or '中转站待确认'}")
            if item.get("total_duration") or item.get("wait_time"):
                parts = [
                    f"总历时：{item.get('total_duration')}" if item.get("total_duration") else "",
                    f"等候：{item.get('wait_time')}" if item.get("wait_time") else "",
                ]
                lines.append("- " + " / ".join(part for part in parts if part))
            segments = list(item.get("segments") or [])
            for seg_index, segment in enumerate(segments[:2], start=1):
                meta = " / ".join(
                    str(part)
                    for part in [
                        segment.get("train_code"),
                        f"{segment.get('from_station')} -> {segment.get('to_station')}",
                        segment.get("start_time"),
                        segment.get("arrive_time"),
                        segment.get("duration"),
                    ]
                    if str(part or "").strip()
                )
                if meta:
                    lines.append(f"- 第 {seg_index} 段：{meta}")
                seats = segment.get("seats") or {}
                if isinstance(seats, dict) and seats:
                    seat_text = " / ".join(
                        f"{name}:{value}"
                        for name, value in list(seats.items())[:5]
                        if str(value or "").strip()
                    )
                    if seat_text:
                        lines.append(f"  - 余票：{seat_text}")
    else:
        lines.extend(
            [
                "",
                "### 查询结果",
                "- 当前 MCP 没有返回可用的一次中转方案。",
                "- 你可以在铁路12306官网/App里切换“中转换乘”继续核验。",
            ]
        )

    lines.extend(
        [
            "",
            "### 官方购票提醒",
            "- 渠道名称：铁路12306官方",
            "- 官网地址：https://www.12306.cn/",
            "- App地址：https://kyfw.12306.cn/otn/appDownload/init",
            "- 购票说明：车次、票价、余票与购票规则请以铁路12306官网/App为准。",
        ]
    )
    return "\n".join(lines)


def _render_arrival_payload(payload: dict) -> str:
    official_notice = payload.get("official_notice") or {}
    provider_status = payload.get("provider_status") or {}
    candidates = payload.get("candidates") or []

    lines = [
        "## 跨城到达建议（12306）",
        f"- 出发城市：{payload.get('origin_city') or '未提供'}",
        f"- 目的城市：{payload.get('destination_city') or '未提供'}",
        f"- 出发日期：{payload.get('depart_date') or '未提供'}",
        f"- 推荐方式：{payload.get('recommended_mode') or '未提供'}",
        f"- 预计耗时：{payload.get('duration_text') or '未提供'}",
        f"- 票价参考：{payload.get('price_text') or '未提供'}",
        f"- 接入状态：{payload.get('booking_status') or 'unknown'}",
        f"- 票务状态：{payload.get('ticket_status') or 'reference'}",
        f"- 数据来源：{payload.get('data_source') or payload.get('provider') or 'unknown'}",
        f"- 数据时效：{payload.get('fetched_at') or '未知'}",
        f"- 方案摘要：{payload.get('summary') or '已生成跨城到达建议'}",
    ]

    if payload.get("degraded_reason"):
        lines.append(f"- 降级原因：{payload.get('degraded_reason')}")

    if provider_status:
        lines.append(f"- 命中来源：{provider_status.get('selected_provider') or '未提供'}")
        fallback_errors = provider_status.get("fallback_errors") or []
        if fallback_errors:
            lines.append("- 降级记录：" + "；".join(str(item) for item in fallback_errors[:3] if str(item).strip()))

    if candidates:
        lines.extend(["", "### 推荐车次"])
        for index, item in enumerate(candidates[:3], start=1):
            train_no = item.get("train_no") or "待补充车次"
            lines.append(f"{index}. {train_no}")

            stations = " -> ".join(
                str(value).strip()
                for value in [item.get("depart_station"), item.get("arrive_station")]
                if str(value or "").strip()
            )
            if stations:
                lines.append(f"- 站点：{stations}")

            meta_parts = [
                item.get("depart_time"),
                item.get("arrive_time"),
                item.get("duration_text"),
                item.get("price_text"),
                item.get("availability_text"),
            ]
            meta = " / ".join(str(part) for part in meta_parts if str(part or "").strip())
            if meta:
                lines.append(f"- 信息：{meta}")

    lines.extend(
        [
            "",
            "### 官方购票提醒",
            f"- 渠道名称：{official_notice.get('channel_name') or '铁路12306官方'}",
            f"- 官网地址：{official_notice.get('website_url') or 'https://www.12306.cn/'}",
            f"- App地址：{official_notice.get('app_url') or 'https://kyfw.12306.cn/otn/appDownload/init'}",
            f"- 购票说明：{official_notice.get('notice') or '车次、票价、余票与购票规则请以铁路12306官网/App为准。'}",
            "",
            "### 补充说明",
        ]
    )

    notes = payload.get("notes") or []
    if not notes:
        notes = ["当前没有更多补充说明。"]
    if payload.get("provider_mode") == "placeholder" or not candidates:
        notes = [
            "当前未拿到实时车次，先给出占位式跨城建议；最终请到 12306 官方核验。",
            *notes,
        ]

    for note in notes:
        if note and str(note).strip():
            lines.append(f"- {note}")

    return "\n".join(lines)


@tool
def plan_12306_arrival(
    origin_city: str,
    destination_city: str,
    depart_date: str = "",
    prefer_high_speed: bool = False,
) -> str:
    """根据出发地、目的地和日期生成跨城到达建议。"""
    try:
        payload = get_train_12306_service().plan_arrival(
            origin_city=origin_city,
            destination_city=destination_city,
            depart_date=depart_date,
        )
    except ValueError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - 兜底保护，避免工具异常打断主链路
        return f"12306 到达规划失败：{exc}"
    if prefer_high_speed:
        payload = _prefer_high_speed_payload(payload)
    return _render_arrival_payload(payload)


def plan_12306_transfer(
    origin_city: str,
    destination_city: str,
    depart_date: str = "",
) -> str:
    """根据出发地、目的地和日期查询一次中转换乘方案。"""
    try:
        payload = MCP12306Provider().search_transfers(
            RailTripQuery(
                origin_city=(origin_city or "").strip(),
                destination_city=(destination_city or "").strip(),
                depart_date=(depart_date or "").strip(),
            )
        )
    except Exception as exc:  # pragma: no cover - 兜底保护，避免打断主链路
        return f"12306 中转方案查询失败：{exc}"
    return _render_transfer_payload(
        payload,
        origin_city=origin_city,
        destination_city=destination_city,
        depart_date=depart_date,
    )


@tool
def query_train_tickets_mcp_12306(
    origin_city: str,
    destination_city: str,
    depart_date: str,
) -> str:
    """直接调用社区 12306 MCP provider，主要用于联调排查。"""
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
    """直接调用免费火车票 provider，主要用于联调排查。"""
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
        return f"免费火车票接口查询失败：{exc}"


@tool
def query_train_tickets_jisu_api(
    origin_city: str,
    destination_city: str,
    depart_date: str,
) -> str:
    """直接调用 Jisu 火车票 provider，主要用于联调排查。"""
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
        return f"Jisu 火车票接口查询失败：{exc}"
