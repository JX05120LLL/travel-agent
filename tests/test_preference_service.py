import unittest
import uuid
from datetime import datetime
from decimal import Decimal

from db.models import UserPreference
from services.chat.preference_service import PreferenceService


def build_preference(
    *,
    category: str,
    key: str,
    label: str,
    source: str = "user_explicit",
    confidence: str = "0.90",
) -> UserPreference:
    preference = UserPreference(
        user_id=uuid.uuid4(),
        preference_category=category,
        preference_key=key,
        preference_value={"value": label, "label": label},
        source=source,
        confidence=Decimal(confidence),
        is_active=True,
    )
    preference.updated_at = datetime(2026, 4, 20, 12, 0, 0)
    return preference


class PreferenceServiceTests(unittest.TestCase):
    def test_current_explicit_preference_suppresses_conflicting_long_term_preference(self):
        service = PreferenceService(db=None)
        long_term_preference = build_preference(
            category="budget",
            key="level",
            label="棰勭畻涓瓑",
            confidence="0.91",
        )

        context = service.build_injection_context(
            preferences=[long_term_preference],
            current_input="杩欐棰勭畻鏈夐檺锛屽敖閲忕渷閽?,
        )

        self.assertEqual(1, len(context["current_explicit"]))
        self.assertEqual("budget.level", context["current_explicit"][0].identity)
        self.assertEqual(0, len(context["effective_preferences"]))
        self.assertEqual(1, len(context["suppressed_preferences"]))
        self.assertEqual(1, len(context["session_overrides"]))
        self.assertEqual(1, len(context["suppressed_conflicts"]))
        self.assertEqual(0, len(context["stable_preferences"]))
        self.assertEqual(0, len(context["flexible_preferences"]))
        self.assertIn("鏈疆鐢ㄦ埛鏄庣‘鎻愬嚭鐨勬柊鍋忓ソ", context["summary"])
        self.assertIn("棰勭畻鍋忕粡娴?, context["summary"])
        self.assertIn("浠ヤ笅闀挎湡鍋忓ソ涓庢湰杞緭鍏ュ啿绐?, context["summary"])


if __name__ == "__main__":
    unittest.main()
