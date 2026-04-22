"""统一导出所有 ORM 模型。

外部依然可以继续使用：
    from db.models import User, ChatSession, Message

这样拆目录之后，调用层不需要一起大改。
"""

from db.models.chat_session import ChatSession
from db.models.history_recall_log import HistoryRecallLog
from db.models.message import Message
from db.models.plan_comparison import PlanComparison
from db.models.plan_comparison_item import PlanComparisonItem
from db.models.plan_option import PlanOption
from db.models.plan_option_destination import PlanOptionDestination
from db.models.session_event import SessionEvent
from db.models.trip import Trip
from db.models.trip_destination import TripDestination
from db.models.trip_itinerary_day import TripItineraryDay
from db.models.user import User
from db.models.user_preference import UserPreference

__all__ = [
    "ChatSession",
    "HistoryRecallLog",
    "Message",
    "PlanComparison",
    "PlanComparisonItem",
    "PlanOption",
    "PlanOptionDestination",
    "SessionEvent",
    "Trip",
    "TripDestination",
    "TripItineraryDay",
    "User",
    "UserPreference",
]
