import importlib.util
import time
import unittest
from unittest.mock import patch


TAVILY_AVAILABLE = importlib.util.find_spec("tavily") is not None


@unittest.skipUnless(TAVILY_AVAILABLE, "tavily 未安装，跳过联网搜索工具测试")
class SearchToolTests(unittest.TestCase):
    @patch("tools.search.TAVILY_TIMEOUT_SECONDS", 1.0)
    @patch("tools.search.os.getenv")
    @patch("tools.search.TavilyClient")
    def test_search_travel_info_returns_degraded_message_on_timeout(
        self,
        mock_client_cls,
        mock_getenv,
    ):
        import tools.search as search_tool

        mock_getenv.side_effect = lambda key, default=None: (
            "test-key" if key == "TAVILY_API_KEY" else default
        )

        class SlowClient:
            def __init__(self, api_key):
                self.api_key = api_key

            def search(self, **kwargs):
                time.sleep(1.2)
                return {"answer": "late"}

        mock_client_cls.side_effect = SlowClient

        result = search_tool.search_travel_info("杭州两天旅行攻略")

        self.assertIn("搜索超时", result)
        self.assertIn("先跳过这一步", result)


if __name__ == "__main__":
    unittest.main()
