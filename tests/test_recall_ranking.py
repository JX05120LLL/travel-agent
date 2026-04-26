import unittest
from datetime import date

from domain.recall.ranking import build_query_profile, score_recall_candidate


class RecallRankingTests(unittest.TestCase):
    def test_build_query_profile_extracts_travel_semantics(self):
        profile = build_query_profile("想找成都亲子3天慢节奏、预算有限的方案")

        self.assertEqual(["成都"], profile.destinations)
        self.assertEqual(3, profile.day_count)
        self.assertEqual("economy", profile.preference_fact_map["budget.level"])
        self.assertEqual("relaxed", profile.preference_fact_map["pace.style"])
        self.assertEqual(
            "family_with_children",
            profile.preference_fact_map["traveler.group"],
        )

    def test_build_query_profile_extracts_holiday_and_season_tags(self):
        profile = build_query_profile("想找国庆去北京的秋天错峰方案")

        self.assertIn("national_day", profile.holiday_labels)
        self.assertIn("autumn", profile.season_tags)
        self.assertIn("off_peak", profile.season_tags)
        self.assertIn("peak_season", profile.season_tags)

    def test_build_query_profile_merges_resolved_holiday_window_dates(self):
        profile = build_query_profile(
            "想找国庆去北京的方案",
            holiday_window={
                "holiday_name": "国庆节",
                "start_date": "2026-10-01",
                "end_date": "2026-10-07",
                "off_day_ranges": [("2026-10-01", "2026-10-07")],
            },
        )

        self.assertIn("national_day", profile.holiday_labels)
        self.assertIn((10, 2), profile.holiday_window_dates)
        self.assertIn(10, profile.travel_months)

    def test_score_recall_candidate_rewards_matching_semantics(self):
        profile = build_query_profile("想找成都亲子3天慢节奏、预算有限的方案")

        matched_score, matched_reasons = score_recall_candidate(
            profile,
            candidate_texts=["成都亲子三天轻松行程，预算有限，适合带孩子"],
            base_score=0.30,
            candidate_destinations=["成都"],
            candidate_preference_facts={
                "budget.level": "economy",
                "pace.style": "relaxed",
                "traveler.group": "family_with_children",
            },
            candidate_day_count=3,
        )

        conflict_score, conflict_reasons = score_recall_candidate(
            profile,
            candidate_texts=["成都三天高预算品质游，节奏紧凑"],
            base_score=0.30,
            candidate_destinations=["成都"],
            candidate_preference_facts={
                "budget.level": "premium",
                "pace.style": "dense",
            },
            candidate_day_count=3,
        )

        self.assertGreater(matched_score, conflict_score)
        self.assertIn("偏好一致:budget.level、pace.style、traveler.group", matched_reasons)
        self.assertIn("天数一致:3天", matched_reasons)
        self.assertIn("偏好冲突:budget.level、pace.style", conflict_reasons)

    def test_score_recall_candidate_rewards_date_month_and_weekend_match(self):
        profile = build_query_profile("想找5月1日出发的杭州周末2天轻松方案")

        matched_score, matched_reasons = score_recall_candidate(
            profile,
            candidate_texts=["杭州五一周末两日轻松游"],
            base_score=0.30,
            candidate_destinations=["杭州"],
            candidate_day_count=2,
            candidate_start_date=date(2026, 5, 1),
            candidate_end_date=date(2026, 5, 2),
            candidate_weekend_trip=True,
        )

        mismatch_score, mismatch_reasons = score_recall_candidate(
            profile,
            candidate_texts=["杭州6月工作日三日游"],
            base_score=0.30,
            candidate_destinations=["杭州"],
            candidate_day_count=3,
            candidate_start_date=date(2026, 6, 10),
            candidate_end_date=date(2026, 6, 12),
            candidate_weekend_trip=False,
        )

        self.assertGreater(matched_score, mismatch_score)
        self.assertIn("具体日期匹配:5月1日", matched_reasons)
        self.assertIn("出行月份匹配:5月", matched_reasons)
        self.assertIn("周末场景匹配", matched_reasons)
        self.assertIn("具体日期未命中", mismatch_reasons)
        self.assertIn("出行月份不一致", mismatch_reasons)
        self.assertIn("非周末场景", mismatch_reasons)

    def test_score_recall_candidate_rewards_holiday_and_season_match(self):
        profile = build_query_profile("想找国庆去北京的秋天错峰方案")

        matched_score, matched_reasons = score_recall_candidate(
            profile,
            candidate_texts=["北京国庆错峰秋游方案"],
            base_score=0.30,
            candidate_destinations=["北京"],
            candidate_holiday_labels={"national_day"},
            candidate_season_tags={"autumn", "off_peak", "peak_season"},
            candidate_start_date=date(2026, 10, 2),
            candidate_end_date=date(2026, 10, 5),
        )

        mismatch_score, mismatch_reasons = score_recall_candidate(
            profile,
            candidate_texts=["北京五一热门档期方案"],
            base_score=0.30,
            candidate_destinations=["北京"],
            candidate_holiday_labels={"labor_day"},
            candidate_season_tags={"spring", "peak_season"},
            candidate_start_date=date(2026, 5, 1),
            candidate_end_date=date(2026, 5, 3),
        )

        self.assertGreater(matched_score, mismatch_score)
        self.assertIn("节假日匹配:national_day", matched_reasons)
        self.assertIn("季节档期匹配:autumn", " ".join(matched_reasons))
        self.assertIn("节假日档期不一致", mismatch_reasons)

    def test_score_recall_candidate_rewards_holiday_window_overlap(self):
        profile = build_query_profile(
            "想找国庆去北京的方案",
            holiday_window={
                "holiday_name": "国庆节",
                "start_date": "2026-10-01",
                "end_date": "2026-10-07",
                "off_day_ranges": [("2026-10-01", "2026-10-07")],
            },
        )

        matched_score, matched_reasons = score_recall_candidate(
            profile,
            candidate_texts=["北京国庆后半段方案"],
            base_score=0.30,
            candidate_destinations=["北京"],
            candidate_start_date=date(2026, 10, 3),
            candidate_end_date=date(2026, 10, 5),
            candidate_holiday_labels={"national_day"},
        )

        mismatch_score, mismatch_reasons = score_recall_candidate(
            profile,
            candidate_texts=["北京节后错峰方案"],
            base_score=0.30,
            candidate_destinations=["北京"],
            candidate_start_date=date(2026, 10, 10),
            candidate_end_date=date(2026, 10, 12),
            candidate_holiday_labels=set(),
        )

        self.assertGreater(matched_score, mismatch_score)
        self.assertIn("节假日窗口重合:", " ".join(matched_reasons))
        self.assertIn("节假日窗口未重合", mismatch_reasons)


if __name__ == "__main__":
    unittest.main()
