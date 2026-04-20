"""候选方案拆分与文本解析规则。

这一层只负责“如何从文本里识别候选方案 / 目的地 / 摘要”，
不关心数据库，也不直接编排业务动作。
"""

from __future__ import annotations

import re

COMMON_DESTINATIONS = [
    "北京",
    "上海",
    "南京",
    "杭州",
    "苏州",
    "成都",
    "重庆",
    "西安",
    "广州",
    "深圳",
    "武汉",
    "长沙",
    "厦门",
    "青岛",
    "哈尔滨",
    "昆明",
    "三亚",
    "洛阳",
    "扬州",
    "镇江",
    "天津",
    "桂林",
]

PLAN_SPLIT_HINT_WORDS = [
    "方案",
    "路线",
    "玩法",
    "版本",
    "option",
    "plan",
    "对比",
    "比较",
    "可选",
    "分别",
    "或者",
    "方向",
    "两种",
    "两版",
    "更适合",
]
MULTI_CITY_ROUTE_HINT_WORDS = [
    "串联",
    "顺路",
    "联程",
    "一起玩",
    "一路",
    "先去",
    "再去",
    "途经",
]
CITY_HEADING_HINT_WORDS = [
    "方案",
    "路线",
    "玩法",
    "版本",
    "推荐",
    "option",
    "plan",
    "城市",
]
ITINERARY_HEADING_HINT_WORDS = [
    "第1天",
    "第2天",
    "第3天",
    "第4天",
    "第5天",
    "第6天",
    "第7天",
    "day 1",
    "day 2",
    "day1",
    "day2",
    "上午",
    "下午",
    "晚上",
    "交通",
]


def normalize_markdown_text(raw_text: str) -> str:
    """把模型输出里的常见不规范 Markdown 先做一遍标准化。"""
    text = str(raw_text or "")
    text = re.sub(r"^(#{1,6})(\*\*|\S)", r"\1 \2", text, flags=re.M)
    text = re.sub(r"^\s*(--|——|––|—{2,})\s*$", "---", text, flags=re.M)
    text = re.sub(r"^(\s*[-*])(\*\*|\S)", r"\1 \2", text, flags=re.M)
    text = re.sub(r"^(\s*\d+\.)((?!\s).)", r"\1 \2", text, flags=re.M)
    return text


def strip_markdown_to_text(raw_text: str) -> str:
    """把 Markdown 内容尽量转成适合预览的纯文本。"""
    text = normalize_markdown_text(raw_text)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s*", "", text, flags=re.M)
    text = re.sub(r"[*_~|#>`]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_plan_summary(content: str) -> str:
    """从 Markdown 内容里提取一段简短摘要。"""
    clean = strip_markdown_to_text(content)
    return clean[:180] if clean else ""


def guess_primary_destination(*texts: str | None) -> str | None:
    """从标题或正文里粗略猜一个主目的地。"""
    combined = " ".join(text for text in texts if text)
    found_items: list[tuple[int, str]] = []
    for city in COMMON_DESTINATIONS:
        position = combined.find(city)
        if position >= 0:
            found_items.append((position, city))

    if not found_items:
        return None

    found_items.sort(key=lambda item: item[0])
    return found_items[0][1]


def extract_mentioned_destinations(*texts: str | None) -> list[str]:
    """按出现顺序提取文本里提到的常见目的地。"""
    combined = " ".join(text for text in texts if text)
    found_items: list[tuple[int, str]] = []
    for city in COMMON_DESTINATIONS:
        position = combined.find(city)
        if position >= 0:
            found_items.append((position, city))

    found_items.sort(key=lambda item: item[0])
    ordered: list[str] = []
    seen: set[str] = set()
    for _, city in found_items:
        if city not in seen:
            ordered.append(city)
            seen.add(city)
    return ordered


def extract_candidate_plan_blocks(content: str) -> list[dict[str, str | None]]:
    """尝试从一条助手回复里拆出多个候选方案块。"""
    normalized = normalize_markdown_text(content)
    lines = normalized.splitlines()
    headings: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        if _is_candidate_plan_heading(line):
            title = re.sub(r"^[#\-\s]+", "", line).strip().strip("*").strip()
            headings.append((index, title))

    if len(headings) < 2:
        return []

    blocks: list[dict[str, str | None]] = []
    for current_index, (start_line, title) in enumerate(headings):
        end_line = headings[current_index + 1][0] if current_index + 1 < len(headings) else len(lines)
        block_lines = lines[start_line:end_line]
        block_text = "\n".join(block_lines).strip()
        if len(strip_markdown_to_text(block_text)) < 20:
            continue
        blocks.append(
            {
                "title": title,
                "plan_markdown": block_text,
                "summary": build_plan_summary(block_text),
                "primary_destination": guess_primary_destination(title, block_text),
            }
        )

    return blocks


def extract_candidate_plan_blocks_with_city_fallback(
    content: str,
) -> list[dict[str, str | None]]:
    """先走显式方案拆分，再走按城市维度的兜底拆分。"""
    candidate_blocks = extract_candidate_plan_blocks(content)
    if candidate_blocks:
        return candidate_blocks

    city_heading_blocks = _extract_city_heading_plan_blocks(content)
    if city_heading_blocks:
        return city_heading_blocks

    city_paragraph_blocks = _extract_city_paragraph_plan_blocks(content)
    if city_paragraph_blocks:
        return city_paragraph_blocks

    return []


def _is_candidate_plan_heading(line: str) -> bool:
    """判断一行文本是不是“候选方案标题”。"""
    plain = line.strip()
    if not plain or len(plain) > 40:
        return False

    plain = re.sub(r"^[#\-\s]+", "", plain).strip()
    plain = plain.strip("*").strip()
    if not plain:
        return False

    if re.match(r"^(方案\s*[一二三四五六七八九十\dA-Za-z]+)", plain, flags=re.I):
        return True

    if re.match(r"^(plan|option|route)\s*[\dA-Za-z]+", plain, flags=re.I):
        return True

    if "方案" in plain and not any(word in plain for word in ["推荐", "总结", "对比", "比较"]):
        return True

    return False


def _looks_like_multi_option_response(content: str) -> bool:
    """粗略判断这段回复是否更像“并行方案”而不是“单方案多城市串联”。"""
    plain_text = strip_markdown_to_text(content).lower()
    has_split_hint = any(word in plain_text for word in PLAN_SPLIT_HINT_WORDS)
    has_multi_city_route_hint = any(
        word in plain_text for word in MULTI_CITY_ROUTE_HINT_WORDS
    )
    return has_split_hint and not has_multi_city_route_hint


def _is_city_plan_heading_line(line: str) -> bool:
    """判断一行文本是否像“按城市拆分的方案标题行”。"""
    plain = re.sub(r"^[#\-\s\d\.\)\(]+", "", line).strip().strip("*").strip()
    if not plain or len(plain) > 36:
        return False

    lower_plain = plain.lower()
    if any(keyword in lower_plain for keyword in ITINERARY_HEADING_HINT_WORDS):
        return False

    mentioned = extract_mentioned_destinations(plain)
    if len(mentioned) != 1:
        return False

    has_heading_prefix = bool(re.match(r"^\s*(#{1,6}|[-*+]|\d+\.)\s*", line))
    has_city_hint = any(word in lower_plain for word in CITY_HEADING_HINT_WORDS)
    if not has_heading_prefix and not has_city_hint:
        return False

    return True


def _extract_city_heading_plan_blocks(content: str) -> list[dict[str, str | None]]:
    """按“城市标题段落”兜底拆分候选方案。"""
    if not _looks_like_multi_option_response(content):
        return []

    normalized = normalize_markdown_text(content)
    lines = normalized.splitlines()
    headings: list[tuple[int, str, str]] = []

    for index, line in enumerate(lines):
        if not _is_city_plan_heading_line(line):
            continue
        clean_title = re.sub(r"^[#\-\s\d\.\)\(]+", "", line).strip().strip("*").strip()
        city_name = (extract_mentioned_destinations(clean_title) or [None])[0]
        if not city_name:
            continue
        headings.append((index, clean_title, city_name))

    if len(headings) < 2:
        return []

    blocks: list[dict[str, str | None]] = []
    for current_index, (start_line, title, city_name) in enumerate(headings):
        end_line = headings[current_index + 1][0] if current_index + 1 < len(headings) else len(lines)
        block_text = "\n".join(lines[start_line:end_line]).strip()
        if len(strip_markdown_to_text(block_text)) < 20:
            continue
        blocks.append(
            {
                "title": title,
                "plan_markdown": block_text,
                "summary": build_plan_summary(block_text),
                "primary_destination": city_name,
            }
        )

    return blocks


def _extract_city_paragraph_plan_blocks(content: str) -> list[dict[str, str | None]]:
    """按段落中的城市归属做更保守的兜底拆分。"""
    if not _looks_like_multi_option_response(content):
        return []

    normalized = normalize_markdown_text(content)
    mentioned_destinations = extract_mentioned_destinations(normalized)
    if len(mentioned_destinations) < 2:
        return []

    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n", normalized)
        if len(strip_markdown_to_text(part)) >= 20
    ]
    if len(paragraphs) < 2:
        return []

    city_paragraphs: dict[str, list[str]] = {city: [] for city in mentioned_destinations}
    shared_intro: list[str] = []
    intro_locked = False

    for paragraph in paragraphs:
        paragraph_cities = extract_mentioned_destinations(paragraph)
        if len(paragraph_cities) == 1:
            city_paragraphs[paragraph_cities[0]].append(paragraph)
            intro_locked = True
            continue
        if not intro_locked and not paragraph_cities:
            shared_intro.append(paragraph)

    blocks: list[dict[str, str | None]] = []
    for city_name, city_parts in city_paragraphs.items():
        merged_parts = [*shared_intro, *city_parts]
        if not city_parts:
            continue
        block_text = "\n\n".join(merged_parts).strip()
        if len(strip_markdown_to_text(block_text)) < 24:
            continue
        plan_markdown = f"## {city_name} 方案\n\n{block_text}"
        blocks.append(
            {
                "title": f"{city_name} 方案",
                "plan_markdown": plan_markdown,
                "summary": build_plan_summary(plan_markdown),
                "primary_destination": city_name,
            }
        )

    return blocks


__all__ = [
    "build_plan_summary",
    "extract_candidate_plan_blocks",
    "extract_candidate_plan_blocks_with_city_fallback",
    "extract_mentioned_destinations",
    "guess_primary_destination",
    "normalize_markdown_text",
    "strip_markdown_to_text",
]
