import unittest

from agent.prompts import build_system_prompt


class AgentPromptTests(unittest.TestCase):
    def test_build_system_prompt_includes_one_stop_planning_rules(self):
        prompt = build_system_prompt("2026年04月23日")

        self.assertIn("一条龙规划", prompt)
        self.assertIn("酒店推荐", prompt)
        self.assertIn("景点间交通", prompt)
        self.assertIn("预算汇总", prompt)
        self.assertIn("本次假设", prompt)
        self.assertIn("amap_plan_spot_routes", prompt)
        self.assertIn("plan_12306_arrival", prompt)
        self.assertIn("search_hotel_stays", prompt)
        self.assertIn("retrieve_local_knowledge", prompt)
        self.assertIn("当前日期：2026年04月23日", prompt)


if __name__ == "__main__":
    unittest.main()
