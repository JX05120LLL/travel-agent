import sys
import types
import unittest

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.get = object
    httpx_module.post = object
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    httpx_module.Response = object
    sys.modules["httpx"] = httpx_module

from services.errors import ServiceIntegrationError
from services.train_12306_service import TuniuFreeApiProvider


class _FakeResponse:
    def __init__(self, *, status_code=200, text="", content_type="application/json", payload=None):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}
        self._payload = payload if payload is not None else {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class Train12306ServiceTests(unittest.TestCase):
    def test_extract_candidates_from_third_party_payload(self):
        payload = {
            "data": {
                "list": [
                    {
                        "station_train_code": "G7311",
                        "from_station_name": "上海虹桥",
                        "to_station_name": "杭州东",
                        "start_time": "07:00",
                        "arrive_time": "08:08",
                        "lishi": "1小时08分钟",
                        "ticketPrice": "73",
                        "ticketNum": "有票",
                    }
                ]
            }
        }

        candidates = TuniuFreeApiProvider._extract_candidates(payload)

        self.assertEqual(1, len(candidates))
        self.assertEqual("G7311", candidates[0].train_no)
        self.assertEqual("上海虹桥", candidates[0].depart_station)
        self.assertEqual("杭州东", candidates[0].arrive_station)
        self.assertEqual("73", candidates[0].price_text)
        self.assertEqual("有票", candidates[0].availability_text)

    def test_parse_json_response_rejects_html_anti_bot_page(self):
        provider = TuniuFreeApiProvider()
        response = _FakeResponse(
            status_code=202,
            text="<html>anti bot</html>",
            content_type="text/html; charset=utf-8",
        )

        with self.assertRaises(ServiceIntegrationError):
            provider._parse_json_response(response)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
