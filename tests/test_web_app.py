import importlib.util
import unittest


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi 未安装，跳过 web.app 相关测试")
class WebAppSmokeTests(unittest.TestCase):
    def test_web_app_can_be_imported(self):
        import web.app as web_app

        self.assertIsNotNone(web_app.app)


if __name__ == "__main__":
    unittest.main()
