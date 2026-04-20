"""用户长期偏好提取规则。

这里放纯规则，尽量不依赖数据库，方便后续继续增强。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class PreferenceCandidate:
    """一条从用户消息中提取出的偏好候选。"""

    category: str
    key: str
    value: dict
    confidence: Decimal
    source: str
    evidence: str

    @property
    def identity(self) -> str:
        """统一偏好主键。"""
        return build_preference_identity(self.category, self.key)


def build_preference_identity(category: str, key: str) -> str:
    """构建统一偏好主键，避免各处重复拼接。"""
    return f"{category}.{key}"


def normalize_preference_value(value: dict | None) -> str | None:
    """把偏好值压缩成适合比较的稳定字符串。"""
    if not isinstance(value, dict):
        return None

    for field in ("value", "label"):
        raw = value.get(field)
        if raw in (None, ""):
            continue
        return str(raw).strip().lower()

    return None


def build_preference_fact_map(
    candidates: list[PreferenceCandidate],
) -> dict[str, str]:
    """把偏好候选压缩成 identity -> normalized_value 的事实映射。"""
    facts: dict[str, str] = {}
    for item in candidates:
        normalized_value = normalize_preference_value(item.value)
        if normalized_value is None:
            continue
        facts[item.identity] = normalized_value
    return facts


def extract_preference_candidates(text: str) -> list[PreferenceCandidate]:
    """从用户文本里提取最小可用的长期偏好候选。"""
    raw = str(text or "")
    candidates: list[PreferenceCandidate] = []

    rules = [
        {
            "signals": ["预算有限", "穷游", "省钱", "性价比", "不要太贵", "便宜点"],
            "category": "budget",
            "key": "level",
            "value": {"value": "economy", "label": "预算偏经济", "priority": "high"},
            "confidence": Decimal("0.9300"),
            "source": "user_explicit",
        },
        {
            "signals": ["预算中等", "中等预算", "预算适中", "预算别太高", "预算普通"],
            "category": "budget",
            "key": "level",
            "value": {"value": "mid", "label": "预算中等", "priority": "high"},
            "confidence": Decimal("0.9000"),
            "source": "user_explicit",
        },
        {
            "signals": ["预算充足", "高预算", "品质游", "住好一点", "酒店好一点"],
            "category": "budget",
            "key": "level",
            "value": {"value": "premium", "label": "预算偏高", "priority": "high"},
            "confidence": Decimal("0.9300"),
            "source": "user_explicit",
        },
        {
            "signals": ["轻松", "不想太赶", "不要太赶", "悠闲", "慢节奏", "别太累", "不想太累"],
            "category": "pace",
            "key": "style",
            "value": {"value": "relaxed", "label": "偏轻松慢节奏", "priority": "high"},
            "confidence": Decimal("0.9200"),
            "source": "user_explicit",
        },
        {
            "signals": ["节奏适中", "平衡一点", "别太赶也别太松", "适中就行"],
            "category": "pace",
            "key": "style",
            "value": {"value": "balanced", "label": "节奏适中", "priority": "medium"},
            "confidence": Decimal("0.8600"),
            "source": "user_explicit",
        },
        {
            "signals": ["紧凑", "特种兵", "多打卡", "行程满一点", "赶一点"],
            "category": "pace",
            "key": "style",
            "value": {"value": "dense", "label": "偏紧凑高密度", "priority": "high"},
            "confidence": Decimal("0.9200"),
            "source": "user_explicit",
        },
        {
            "signals": ["亲子", "带孩子", "小朋友"],
            "category": "traveler",
            "key": "group",
            "value": {"value": "family_with_children", "label": "亲子出行", "priority": "high"},
            "confidence": Decimal("0.9500"),
            "source": "user_explicit",
        },
        {
            "signals": ["带老人", "老人出行", "长辈"],
            "category": "traveler",
            "key": "group",
            "value": {"value": "with_elders", "label": "带老人出行", "priority": "high"},
            "confidence": Decimal("0.9500"),
            "source": "user_explicit",
        },
        {
            "signals": ["美食", "吃吃吃", "小吃", "想吃", "好吃的"],
            "category": "interest",
            "key": "food",
            "value": {"value": True, "label": "偏好美食", "priority": "medium"},
            "confidence": Decimal("0.8300"),
            "source": "derived",
        },
        {
            "signals": ["夜景", "夜游", "晚上逛", "夜拍"],
            "category": "interest",
            "key": "night_view",
            "value": {"value": True, "label": "偏好夜景", "priority": "medium"},
            "confidence": Decimal("0.8000"),
            "source": "derived",
        },
        {
            "signals": ["拍照", "出片", "摄影", "拍照好看"],
            "category": "interest",
            "key": "photo",
            "value": {"value": True, "label": "偏好拍照出片", "priority": "medium"},
            "confidence": Decimal("0.8200"),
            "source": "derived",
        },
        {
            "signals": ["靠近地铁", "地铁口", "交通方便"],
            "category": "stay",
            "key": "near_metro",
            "value": {"value": True, "label": "住宿偏好靠近地铁", "priority": "high"},
            "confidence": Decimal("0.8800"),
            "source": "user_explicit",
        },
        {
            "signals": ["安静一点", "别太吵", "安静的酒店"],
            "category": "stay",
            "key": "quiet",
            "value": {"value": True, "label": "住宿偏好安静", "priority": "high"},
            "confidence": Decimal("0.8700"),
            "source": "user_explicit",
        },
    ]

    for rule in rules:
        hit_signal = next((signal for signal in rule["signals"] if signal in raw), None)
        if hit_signal is None:
            continue
        candidates.append(
            PreferenceCandidate(
                category=rule["category"],
                key=rule["key"],
                value={**rule["value"], "evidence": hit_signal},
                confidence=rule["confidence"],
                source=rule["source"],
                evidence=hit_signal,
            )
        )

    deduped: dict[str, PreferenceCandidate] = {}
    for item in candidates:
        existing = deduped.get(item.identity)
        if existing is None or item.confidence >= existing.confidence:
            deduped[item.identity] = item

    return list(deduped.values())
