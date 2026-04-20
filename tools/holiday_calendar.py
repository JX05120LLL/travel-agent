"""
节假日与工作日工具
==================

基于 jiejiariapi 封装中国节假日查询能力。

目标：
- 给 Agent 提供高层能力，而不是只暴露底层 REST 接口
- 支持查询某年节假日安排
- 支持解析“五一 / 国庆 / 春节”等节日日期窗口
- 支持判断某一天是不是节假日 / 调休日
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

load_dotenv()

JIEJIARI_API_BASE = os.getenv("JIEJIARI_API_BASE", "https://api.jiejiariapi.com").rstrip("/")

HOLIDAY_ALIASES = {
    "元旦": ["元旦"],
    "春节": ["春节"],
    "清明节": ["清明", "清明节"],
    "劳动节": ["劳动节", "五一"],
    "端午节": ["端午", "端午节"],
    "中秋节": ["中秋", "中秋节"],
    "国庆节": ["国庆", "国庆节", "十一"],
}


def contains_holiday_keyword(text: str) -> bool:
    """Check whether text contains a known holiday keyword."""
    return _match_holiday_name(text) is not None


def _build_headers() -> dict:
    """Build optional auth headers for jiejiari api."""
    headers = {"Accept": "application/json"}
    api_key = os.getenv("JIEJIARI_API_KEY", "").strip()
    if api_key:
        # Keep this optional; free tier requests can still work without it.
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _fetch_json(url: str, *, params: dict | None = None) -> dict:
    """Call jiejiari api and return json."""
    response = httpx.get(url, headers=_build_headers(), params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _resolve_year(query_text: str, year_hint: str) -> int:
    """Resolve target year from explicit year or relative words."""
    today = date.today()
    if year_hint.strip().isdigit():
        return int(year_hint.strip())

    year_match = re.search(r"(20\d{2})年?", query_text)
    if year_match:
        return int(year_match.group(1))

    if "明年" in query_text:
        return today.year + 1
    if "后年" in query_text:
        return today.year + 2
    if "去年" in query_text:
        return today.year - 1

    return today.year


def _extract_exact_date(query_text: str) -> str | None:
    """Extract exact date in YYYY-MM-DD format."""
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", query_text)
    if match:
        return match.group(1)
    return None


def _match_holiday_name(query_text: str) -> str | None:
    """Match user text to canonical holiday name."""
    for canonical_name, aliases in HOLIDAY_ALIASES.items():
        if any(alias in query_text for alias in aliases):
            return canonical_name
    return None


def _group_holiday_ranges(holiday_data: dict, canonical_name: str) -> list[tuple[str, str, list[dict]]]:
    """Group consecutive holiday entries into ranges."""
    matched_items = []
    aliases = HOLIDAY_ALIASES.get(canonical_name, [canonical_name])
    for item in holiday_data.values():
        item_name = str(item.get("name", ""))
        if any(alias in item_name for alias in aliases):
            matched_items.append(item)

    matched_items.sort(key=lambda x: x["date"])
    if not matched_items:
        return []

    ranges: list[tuple[str, str, list[dict]]] = []
    current_group = [matched_items[0]]

    for item in matched_items[1:]:
        prev_date = datetime.strptime(current_group[-1]["date"], "%Y-%m-%d").date()
        curr_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
        if curr_date - prev_date == timedelta(days=1):
            current_group.append(item)
        else:
            ranges.append((current_group[0]["date"], current_group[-1]["date"], current_group[:]))
            current_group = [item]

    ranges.append((current_group[0]["date"], current_group[-1]["date"], current_group[:]))
    return ranges


def _group_consecutive_dates(date_list: list[str]) -> list[tuple[str, str]]:
    """Group sorted date strings into consecutive ranges."""
    if not date_list:
        return []

    sorted_dates = sorted(date_list)
    groups: list[tuple[str, str]] = []
    start = sorted_dates[0]
    end = sorted_dates[0]

    for current in sorted_dates[1:]:
        prev_date = datetime.strptime(end, "%Y-%m-%d").date()
        curr_date = datetime.strptime(current, "%Y-%m-%d").date()
        if curr_date - prev_date == timedelta(days=1):
            end = current
        else:
            groups.append((start, end))
            start = current
            end = current

    groups.append((start, end))
    return groups


def _format_year_summary(year: int, holiday_data: dict) -> str:
    """Format main holiday windows for a year."""
    lines = [f"【{year}年中国主要节假日安排】"]

    for canonical_name in [
        "元旦",
        "春节",
        "清明节",
        "劳动节",
        "端午节",
        "中秋节",
        "国庆节",
    ]:
        ranges = _group_holiday_ranges(holiday_data, canonical_name)
        if not ranges:
            continue

        range_strings = []
        for start, end, items in ranges:
            off_days = sum(1 for item in items if item.get("isOffDay"))
            range_strings.append(f"{start} 至 {end}（共 {len(items)} 天，其中休息日 {off_days} 天）")
        lines.append(f"- {canonical_name}：{'；'.join(range_strings)}")

    lines.append("")
    lines.append("提示：接口返回里既包含放假日，也可能包含调休日或节日前后相关日期，具体要结合 isOffDay 判断。")
    return "\n".join(lines)


def _format_holiday_window(year: int, canonical_name: str, holiday_data: dict, query_text: str) -> str:
    """Format one holiday window."""
    ranges = _group_holiday_ranges(holiday_data, canonical_name)
    if not ranges:
        return f"没有查到 {year} 年 {canonical_name} 的节假日数据。"

    lines = [f"【{year}年{canonical_name}安排】"]

    requested_days_match = re.search(r"(\d+)\s*(天|日)", query_text)
    requested_days = int(requested_days_match.group(1)) if requested_days_match else None

    off_days_all: list[str] = []
    work_days_all: list[str] = []
    for _, _, items in ranges:
        off_days_all.extend(item["date"] for item in items if item.get("isOffDay"))
        work_days_all.extend(item["date"] for item in items if not item.get("isOffDay"))

    off_ranges = _group_consecutive_dates(sorted(set(off_days_all)))
    if off_ranges:
        lines.append("- 官方休息日窗口：")
        for start, end in off_ranges:
            if start == end:
                lines.append(f"  - {start}")
            else:
                lines.append(f"  - {start} 至 {end}")

    if work_days_all:
        lines.append("- 相关调休日/非休息日：")
        for current in sorted(set(work_days_all)):
            lines.append(f"  - {current}")

    if requested_days is not None:
        lines.append(f"- 你提到的是 {requested_days} 天，这个节日窗口里休息日共 {len(set(off_days_all))} 天。")

    lines.append("")
    lines.append("如果后面要继续查这段时间的天气、酒店或路线，可以把这里的起止日期直接传给后续工具。")
    return "\n".join(lines)


def _format_day_type(day: str, result: dict) -> str:
    """Format exact day holiday/workday result."""
    holiday = result.get("holiday") or {}
    is_holiday = result.get("is_holiday")
    holiday_name = holiday.get("name", "未知")
    is_off_day = holiday.get("isOffDay")

    lines = [f"【{day} 日期判断】"]
    lines.append(f"- 节假日判断：{'是' if is_holiday else '否'}")
    lines.append(f"- 节日名称：{holiday_name}")
    if is_off_day is True:
        lines.append("- 是否休息日：是")
    elif is_off_day is False:
        lines.append("- 是否休息日：否，可能是调休日或普通工作日")
    else:
        lines.append("- 是否休息日：接口未明确返回")
    return "\n".join(lines)


def resolve_holiday_window(query_text: str, year_hint: str = "") -> dict | None:
    """
    Resolve a holiday expression into a structured date window.

    This helper is for internal tool orchestration, for example:
    - weather tool needs exact dates before querying forecast
    - future date resolution service needs official holiday windows
    """
    query_text = (query_text or "").strip()
    if not query_text:
        return None

    holiday_name = _match_holiday_name(query_text)
    if not holiday_name:
        return None

    def build_window(target_year: int) -> dict | None:
        holidays_url = f"{JIEJIARI_API_BASE}/v1/holidays/{target_year}"
        try:
            holiday_data = _fetch_json(holidays_url)
        except Exception:
            return None

        ranges = _group_holiday_ranges(holiday_data, holiday_name)
        if not ranges:
            return None

        off_days_all: list[str] = []
        work_days_all: list[str] = []
        for _, _, items in ranges:
            off_days_all.extend(item["date"] for item in items if item.get("isOffDay"))
            work_days_all.extend(item["date"] for item in items if not item.get("isOffDay"))

        off_ranges = _group_consecutive_dates(sorted(set(off_days_all)))
        if not off_ranges:
            return None

        main_start, main_end = max(
            off_ranges,
            key=lambda item: (
                datetime.strptime(item[1], "%Y-%m-%d").date()
                - datetime.strptime(item[0], "%Y-%m-%d").date()
            ).days,
        )

        return {
            "holiday_name": holiday_name,
            "year": target_year,
            "start_date": main_start,
            "end_date": main_end,
            "off_day_ranges": off_ranges,
            "work_days": sorted(set(work_days_all)),
        }

    year = _resolve_year(query_text, year_hint)
    window = build_window(year)
    if not window:
        return None

    today = date.today()
    has_explicit_year = bool(year_hint.strip()) or bool(re.search(r"(20\d{2})年?", query_text))
    if not has_explicit_year:
        end_dt = datetime.strptime(window["end_date"], "%Y-%m-%d").date()
        if end_dt < today:
            next_window = build_window(year + 1)
            if next_window:
                return next_window

    return window


@tool
def resolve_holiday_dates(query_text: str, year_hint: str = "") -> str:
    """
    查询中国节假日和工作日信息。

    适用场景：
    - 查询某年节假日安排
    - 查询五一、国庆、春节、中秋等节日具体放哪几天
    - 查询某一天是不是节假日、是不是调休日

    参数：
    - query_text: 用户原始问题，例如“今年国庆放哪几天”“2026-10-01 是不是节假日”“明年五一假期安排”
    - year_hint: 可选，显式传年份，例如“2026”
    """
    query_text = query_text.strip()
    if not query_text:
        return "错误：query_text 不能为空。"

    exact_date = _extract_exact_date(query_text)
    if exact_date:
        url = f"{JIEJIARI_API_BASE}/v1/is_holiday"
        try:
            result = _fetch_json(url, params={"date": exact_date})
        except httpx.HTTPStatusError as exc:
            return f"查询日期类型失败：HTTP {exc.response.status_code}，{exc.response.text}"
        except Exception as exc:
            return f"查询日期类型失败：{exc}"
        return _format_day_type(exact_date, result)

    year = _resolve_year(query_text, year_hint)
    holidays_url = f"{JIEJIARI_API_BASE}/v1/holidays/{year}"
    try:
        holiday_data = _fetch_json(holidays_url)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return (
                f"暂时没有查到 {year} 年的节假日数据，可能是该年度官方安排还没发布，"
                "或者 jiejiari api 还没有同步。"
            )
        return f"查询节假日安排失败：HTTP {exc.response.status_code}，{exc.response.text}"
    except Exception as exc:
        return f"查询节假日安排失败：{exc}"

    holiday_name = _match_holiday_name(query_text)
    if holiday_name:
        return _format_holiday_window(year, holiday_name, holiday_data, query_text)

    if any(keyword in query_text for keyword in ["节假日", "放假", "假期安排", "法定假日"]):
        return _format_year_summary(year, holiday_data)

    supported = "、".join(["元旦", "春节", "清明", "五一/劳动节", "端午", "中秋", "国庆", "具体日期"])
    return (
        f"暂时没法从这句话里判断你要查哪类节假日：{query_text}\n"
        f"当前支持的查询类型包括：{supported}。\n"
        "你也可以直接问：\n"
        "- 今年国庆放哪几天\n"
        "- 2026年节假日安排\n"
        "- 2026-10-01 是不是节假日"
    )
