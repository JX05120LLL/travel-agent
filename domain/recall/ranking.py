"""历史召回排序规则。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from domain.memory.preference_rules import (
    build_preference_fact_map,
    extract_preference_candidates,
)
from domain.plan_option.splitters import extract_mentioned_destinations, strip_markdown_to_text

CHINESE_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

HOLIDAY_ALIASES = {
    "new_year": ["元旦", "新年", "跨年"],
    "spring_festival": ["春节", "过年"],
    "qingming": ["清明", "清明节"],
    "labor_day": ["五一", "劳动节"],
    "dragon_boat": ["端午", "端午节"],
    "mid_autumn": ["中秋", "中秋节"],
    "national_day": ["国庆", "国庆节", "十一", "黄金周"],
}

MONTH_TO_SEASON = {
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "autumn",
    10: "autumn",
    11: "autumn",
    12: "winter",
}

SEASON_KEYWORDS = {
    "spring": ["春天", "春季", "踏青", "赏花"],
    "summer": ["夏天", "夏季", "避暑"],
    "autumn": ["秋天", "秋季", "秋游", "赏秋"],
    "winter": ["冬天", "冬季", "滑雪", "泡温泉"],
    "summer_vacation": ["暑假", "暑期"],
    "winter_vacation": ["寒假", "寒假期间"],
    "peak_season": ["旺季", "热门档期", "黄金周"],
    "off_peak": ["淡季", "错峰", "避开人多"],
}

FIXED_HOLIDAY_MONTH_DAY = {
    "new_year": {(1, 1)},
    "labor_day": {(5, 1)},
    "national_day": {(10, 1)},
}


@dataclass(slots=True)
class RecallQueryProfile:
    """召回查询画像。"""

    cleaned_query: str
    query_tokens: set[str]
    destinations: list[str]
    preference_identities: set[str]
    preference_fact_map: dict[str, str]
    day_count: int | None
    specific_dates: set[tuple[int, int]]
    holiday_window_dates: set[tuple[int, int]]
    travel_months: set[int]
    weekend_trip: bool | None
    holiday_labels: set[str]
    season_tags: set[str]


def build_query_profile(
    query_text: str,
    *,
    holiday_window: dict | None = None,
) -> RecallQueryProfile:
    """把原始查询解析成更适合打分的结构。"""
    cleaned_query = " ".join(strip_markdown_to_text(query_text).split()).strip()
    preference_candidates = extract_preference_candidates(query_text)
    preference_fact_map = build_preference_fact_map(preference_candidates)
    query_tokens = tokenize_recall_text(cleaned_query)
    destinations = extract_mentioned_destinations(query_text)

    for city in destinations:
        query_tokens.add(city.lower())
    for item in preference_candidates:
        query_tokens.add(item.category.lower())
        query_tokens.add(item.key.lower())
        label = str(item.value.get("label") or "").strip().lower()
        if label:
            query_tokens.add(label)

    day_count = extract_day_count(query_text)
    if day_count is not None:
        query_tokens.add(f"{day_count}天")
    specific_dates = extract_specific_dates(query_text)
    holiday_window_dates = collect_dates_from_holiday_window(holiday_window)
    travel_months = extract_month_numbers(query_text) | {
        month for month, _ in specific_dates
    }
    travel_months |= {month for month, _ in holiday_window_dates}
    weekend_trip = infer_weekend_trip(query_text)
    holiday_labels = extract_holiday_labels(
        query_text,
        specific_dates=specific_dates | holiday_window_dates,
        holiday_window=holiday_window,
    )
    season_tags = infer_season_tags(
        query_text,
        months=travel_months,
        holiday_labels=holiday_labels,
    )

    return RecallQueryProfile(
        cleaned_query=cleaned_query,
        query_tokens=query_tokens,
        destinations=destinations,
        preference_identities={item.identity for item in preference_candidates},
        preference_fact_map=preference_fact_map,
        day_count=day_count,
        specific_dates=specific_dates,
        holiday_window_dates=holiday_window_dates,
        travel_months=travel_months,
        weekend_trip=weekend_trip,
        holiday_labels=holiday_labels,
        season_tags=season_tags,
    )


def tokenize_recall_text(*texts: str | None) -> set[str]:
    """把文本切成一个朴素但稳定的召回 token 集合。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)
    lowered = merged.lower()
    tokens: set[str] = set()

    for token in re.findall(r"[a-z0-9]{2,}", lowered):
        tokens.add(token)

    for part in re.split(r"[\s,，。；;、/（）()\n-]+", lowered):
        part = part.strip()
        if not part:
            continue
        if re.search(r"[\u4e00-\u9fff]", part) and 1 < len(part) <= 10:
            tokens.add(part)

    return tokens


def extract_day_count(*texts: str | None) -> int | None:
    """从查询或候选文本中提取天数，优先取最明确的匹配。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)

    weekend_match = re.search(r"周末", merged)
    explicit_digit_match = re.search(r"(\d{1,2})\s*(?:天|日)", merged)
    if explicit_digit_match:
        return int(explicit_digit_match.group(1))

    explicit_cn_match = re.search(r"([一二两三四五六七八九十]{1,3})\s*(?:天|日)", merged)
    if explicit_cn_match:
        return chinese_number_to_int(explicit_cn_match.group(1))

    if weekend_match:
        return 2

    return None


def extract_specific_dates(*texts: str | None) -> set[tuple[int, int]]:
    """提取文本里出现的“月-日”日期片段。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)
    dates: set[tuple[int, int]] = set()
    for month_raw, day_raw in re.findall(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", merged):
        month = int(month_raw)
        day = int(day_raw)
        if 1 <= month <= 12 and 1 <= day <= 31:
            dates.add((month, day))
    return dates


def extract_month_numbers(*texts: str | None) -> set[int]:
    """提取文本中出现的月份。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)
    months: set[int] = set()
    for raw_month in re.findall(r"(\d{1,2})\s*月", merged):
        month = int(raw_month)
        if 1 <= month <= 12:
            months.add(month)
    return months


def extract_holiday_labels(
    *texts: str | None,
    specific_dates: set[tuple[int, int]] | None = None,
    holiday_window: dict | None = None,
) -> set[str]:
    """提取节假日标签，优先用显式关键词，其次用少量稳定的固定节日日期推断。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)
    labels: set[str] = set()

    for canonical_name, aliases in HOLIDAY_ALIASES.items():
        if any(alias in merged for alias in aliases):
            labels.add(canonical_name)

    for month_day in specific_dates or set():
        for canonical_name, candidates in FIXED_HOLIDAY_MONTH_DAY.items():
            if month_day in candidates:
                labels.add(canonical_name)

    holiday_name = str((holiday_window or {}).get("holiday_name") or "").strip()
    normalized_holiday_name = normalize_holiday_label(holiday_name)
    if normalized_holiday_name:
        labels.add(normalized_holiday_name)

    return labels


def normalize_holiday_label(raw_name: str | None) -> str | None:
    """把中文节假日名称统一成 ranking 内部使用的标签。"""
    clean_name = str(raw_name or "").strip()
    if not clean_name:
        return None
    for canonical_name, aliases in HOLIDAY_ALIASES.items():
        if clean_name == canonical_name or clean_name in aliases:
            return canonical_name
    return None


def infer_season_tags(
    *texts: str | None,
    months: set[int] | None = None,
    holiday_labels: set[str] | None = None,
) -> set[str]:
    """根据文本、月份和节假日推断季节/档期标签。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)
    season_tags: set[str] = set()

    for tag, keywords in SEASON_KEYWORDS.items():
        if any(keyword in merged for keyword in keywords):
            season_tags.add(tag)

    for month in months or set():
        season = MONTH_TO_SEASON.get(month)
        if season:
            season_tags.add(season)
        if month in {7, 8}:
            season_tags.add("summer_vacation")
        if month in {1, 2}:
            season_tags.add("winter_vacation")

    holiday_labels = holiday_labels or set()
    if holiday_labels & {"labor_day", "national_day", "spring_festival"}:
        season_tags.add("peak_season")
    if "labor_day" in holiday_labels:
        season_tags.add("spring")
    if "national_day" in holiday_labels:
        season_tags.add("autumn")
    if "new_year" in holiday_labels or "spring_festival" in holiday_labels:
        season_tags.add("winter")

    return season_tags


def collect_months_from_date_range(
    start_date: date | None,
    end_date: date | None,
) -> set[int]:
    """从结构化日期范围里提取涉及到的月份。"""
    if start_date is None and end_date is None:
        return set()

    if start_date is None:
        start_date = end_date
    if end_date is None:
        end_date = start_date
    if start_date is None or end_date is None:
        return set()

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    months = {start_date.month, end_date.month}
    current = start_date
    while current <= end_date and len(months) < 12:
        months.add(current.month)
        current += timedelta(days=1)
    return months


def collect_specific_dates_from_date_range(
    start_date: date | None,
    end_date: date | None,
) -> set[tuple[int, int]]:
    """从结构化日期范围里提取明确日期，用于高置信度日期匹配。"""
    if start_date is None and end_date is None:
        return set()

    if start_date is None:
        start_date = end_date
    if end_date is None:
        end_date = start_date
    if start_date is None or end_date is None:
        return set()

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    dates = {(start_date.month, start_date.day), (end_date.month, end_date.day)}
    return dates


def collect_day_points_from_date_range(
    start_date: date | None,
    end_date: date | None,
    *,
    max_days: int = 31,
) -> set[tuple[int, int]]:
    """把结构化日期范围展开成月-日点集合，适合做假期窗口重合判断。"""
    if start_date is None and end_date is None:
        return set()

    if start_date is None:
        start_date = end_date
    if end_date is None:
        end_date = start_date
    if start_date is None or end_date is None:
        return set()

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    days = (end_date - start_date).days + 1
    if days > max_days:
        return collect_specific_dates_from_date_range(start_date, end_date)

    points: set[tuple[int, int]] = set()
    current = start_date
    while current <= end_date:
        points.add((current.month, current.day))
        current += timedelta(days=1)
    return points


def collect_dates_from_holiday_window(holiday_window: dict | None) -> set[tuple[int, int]]:
    """把 holiday_window 里的放假日期窗转成可比较的月-日集合。"""
    if not holiday_window:
        return set()

    collected_dates: set[tuple[int, int]] = set()
    for start_raw, end_raw in holiday_window.get("off_day_ranges") or []:
        try:
            start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        collected_dates |= collect_day_points_from_date_range(start_date, end_date)

    if collected_dates:
        return collected_dates

    start_raw = holiday_window.get("start_date")
    end_raw = holiday_window.get("end_date")
    try:
        start_date = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else None
        end_date = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else None
    except ValueError:
        return set()
    return collect_day_points_from_date_range(start_date, end_date)


def infer_weekend_trip(
    *texts: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> bool | None:
    """识别是否是典型周末出行场景。"""
    merged = " ".join(strip_markdown_to_text(text or "") for text in texts if text)
    if any(keyword in merged for keyword in ["周末", "周六", "周日", "双休"]):
        return True
    if any(keyword in merged for keyword in ["工作日", "请假", "年假", "调休"]):
        return False

    if start_date is None and end_date is None:
        return None

    if start_date is None:
        start_date = end_date
    if end_date is None:
        end_date = start_date
    if start_date is None or end_date is None:
        return None

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    duration_days = (end_date - start_date).days + 1
    if duration_days > 3:
        return None

    current = start_date
    while current <= end_date:
        if current.weekday() >= 5:
            return True
        current += timedelta(days=1)
    return False


def chinese_number_to_int(raw: str) -> int | None:
    """把常见的中文数字转成整数，目前只处理旅行天数够用的范围。"""
    text = str(raw or "").strip()
    if not text:
        return None
    if text == "十":
        return 10
    if "十" not in text:
        return CHINESE_NUMBER_MAP.get(text)

    left, _, right = text.partition("十")
    tens = CHINESE_NUMBER_MAP.get(left, 1) if left else 1
    ones = CHINESE_NUMBER_MAP.get(right, 0) if right else 0
    return tens * 10 + ones


def score_recall_candidate(
    profile: RecallQueryProfile,
    *,
    candidate_texts: list[str | None],
    base_score: float,
    candidate_destinations: list[str] | None = None,
    candidate_preference_identities: set[str] | None = None,
    candidate_preference_facts: dict[str, str] | None = None,
    candidate_day_count: int | None = None,
    candidate_specific_dates: set[tuple[int, int]] | None = None,
    candidate_travel_months: set[int] | None = None,
    candidate_weekend_trip: bool | None = None,
    candidate_start_date: date | None = None,
    candidate_end_date: date | None = None,
    candidate_holiday_labels: set[str] | None = None,
    candidate_season_tags: set[str] | None = None,
) -> tuple[float, list[str]]:
    """根据查询画像为候选记录打分。"""
    combined = " ".join(text for text in candidate_texts if text)
    cleaned_candidate = " ".join(strip_markdown_to_text(combined).split()).strip()
    candidate_tokens = tokenize_recall_text(cleaned_candidate)
    candidate_destinations = candidate_destinations or []

    # 即使上层没有传结构化偏好，也尽量从候选文本中恢复旅行语义。
    inferred_candidate_facts = build_preference_fact_map(
        extract_preference_candidates(cleaned_candidate)
    )
    merged_candidate_facts = dict(inferred_candidate_facts)
    merged_candidate_facts.update(candidate_preference_facts or {})
    merged_candidate_identities = set(candidate_preference_identities or set()) | set(
        merged_candidate_facts.keys()
    )
    resolved_candidate_day_count = candidate_day_count or extract_day_count(cleaned_candidate)
    resolved_candidate_specific_dates = set(candidate_specific_dates or set()) | extract_specific_dates(
        cleaned_candidate
    )
    resolved_candidate_specific_dates |= collect_specific_dates_from_date_range(
        candidate_start_date,
        candidate_end_date,
    )
    resolved_candidate_range_dates = collect_day_points_from_date_range(
        candidate_start_date,
        candidate_end_date,
    )
    resolved_candidate_range_dates |= resolved_candidate_specific_dates
    resolved_candidate_travel_months = set(candidate_travel_months or set()) | extract_month_numbers(
        cleaned_candidate
    )
    resolved_candidate_travel_months |= {
        month for month, _ in resolved_candidate_specific_dates
    }
    resolved_candidate_travel_months |= collect_months_from_date_range(
        candidate_start_date,
        candidate_end_date,
    )
    resolved_candidate_holiday_labels = set(candidate_holiday_labels or set()) | extract_holiday_labels(
        cleaned_candidate,
        specific_dates=resolved_candidate_specific_dates,
    )
    resolved_candidate_weekend_trip = (
        candidate_weekend_trip
        if candidate_weekend_trip is not None
        else infer_weekend_trip(
            cleaned_candidate,
            start_date=candidate_start_date,
            end_date=candidate_end_date,
        )
    )
    resolved_candidate_season_tags = set(candidate_season_tags or set()) | infer_season_tags(
        cleaned_candidate,
        months=resolved_candidate_travel_months,
        holiday_labels=resolved_candidate_holiday_labels,
    )

    score = base_score
    reasons: list[str] = []

    if profile.cleaned_query and profile.cleaned_query in cleaned_candidate:
        score += 0.22
        reasons.append("命中完整查询")

    destination_overlap = [
        city
        for city in profile.destinations
        if city in candidate_destinations or city in combined
    ]
    if destination_overlap:
        score += min(0.24 * len(destination_overlap), 0.48)
        reasons.append("目的地匹配:" + "、".join(destination_overlap))

    token_overlap = sorted(profile.query_tokens & candidate_tokens)
    if token_overlap:
        score += min(0.05 * len(token_overlap), 0.20)
        reasons.append("关键词重合:" + "、".join(token_overlap[:4]))

    matched_preference_facts = sorted(
        key
        for key, value in profile.preference_fact_map.items()
        if merged_candidate_facts.get(key) == value
    )
    conflicting_preference_facts = sorted(
        key
        for key, value in profile.preference_fact_map.items()
        if key in merged_candidate_facts and merged_candidate_facts.get(key) != value
    )
    identity_only_overlap = sorted(
        profile.preference_identities & merged_candidate_identities
        - set(matched_preference_facts)
        - set(conflicting_preference_facts)
    )

    if matched_preference_facts:
        score += min(0.16 * len(matched_preference_facts), 0.32)
        reasons.append("偏好一致:" + "、".join(matched_preference_facts))

    if identity_only_overlap:
        score += min(0.08 * len(identity_only_overlap), 0.16)
        reasons.append("偏好同类重合:" + "、".join(identity_only_overlap))

    if conflicting_preference_facts:
        score -= min(0.12 * len(conflicting_preference_facts), 0.24)
        reasons.append("偏好冲突:" + "、".join(conflicting_preference_facts))

    if profile.day_count is not None and resolved_candidate_day_count is not None:
        day_diff = abs(profile.day_count - resolved_candidate_day_count)
        if day_diff == 0:
            score += 0.12
            reasons.append(f"天数一致:{profile.day_count}天")
        elif day_diff == 1:
            score += 0.05
            reasons.append(
                f"天数接近:{profile.day_count}天 vs {resolved_candidate_day_count}天"
            )
        else:
            score -= 0.05
            reasons.append(
                f"天数偏差较大:{profile.day_count}天 vs {resolved_candidate_day_count}天"
            )

    if profile.specific_dates and resolved_candidate_specific_dates:
        date_overlap = sorted(profile.specific_dates & resolved_candidate_specific_dates)
        if date_overlap:
            score += min(0.18 * len(date_overlap), 0.24)
            reasons.append(
                "具体日期匹配:"
                + "、".join(f"{month}月{day}日" for month, day in date_overlap[:2])
            )
        else:
            score -= 0.06
            reasons.append("具体日期未命中")

    if profile.holiday_window_dates and resolved_candidate_range_dates:
        holiday_window_overlap = sorted(
            profile.holiday_window_dates & resolved_candidate_range_dates
        )
        if holiday_window_overlap:
            score += min(0.14 * len(holiday_window_overlap), 0.22)
            reasons.append(
                "节假日窗口重合:"
                + "、".join(
                    f"{month}月{day}日" for month, day in holiday_window_overlap[:3]
                )
            )
        else:
            score -= 0.05
            reasons.append("节假日窗口未重合")

    if profile.travel_months and resolved_candidate_travel_months:
        month_overlap = sorted(profile.travel_months & resolved_candidate_travel_months)
        if month_overlap:
            score += min(0.08 * len(month_overlap), 0.16)
            reasons.append("出行月份匹配:" + "、".join(f"{month}月" for month in month_overlap))
        else:
            score -= 0.04
            reasons.append("出行月份不一致")

    if profile.weekend_trip is True:
        if resolved_candidate_weekend_trip is True:
            score += 0.08
            reasons.append("周末场景匹配")
        elif resolved_candidate_weekend_trip is False:
            score -= 0.06
            reasons.append("非周末场景")

    if profile.holiday_labels:
        holiday_overlap = sorted(profile.holiday_labels & resolved_candidate_holiday_labels)
        if holiday_overlap:
            score += min(0.12 * len(holiday_overlap), 0.18)
            reasons.append("节假日匹配:" + "、".join(holiday_overlap))
        elif resolved_candidate_holiday_labels:
            score -= 0.06
            reasons.append("节假日档期不一致")

    if profile.season_tags:
        season_overlap = sorted(profile.season_tags & resolved_candidate_season_tags)
        if season_overlap:
            score += min(0.05 * len(season_overlap), 0.12)
            reasons.append("季节档期匹配:" + "、".join(season_overlap[:3]))
        elif resolved_candidate_season_tags:
            score -= 0.03
            reasons.append("季节档期不一致")

    if profile.destinations and not destination_overlap:
        score -= 0.06

    return max(0.0, min(score, 0.99)), reasons
