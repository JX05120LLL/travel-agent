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
    sys.modules["httpx"] = httpx_module

from services.errors import ServiceConfigError
from services.hotel_service import (
    AmapStayFallbackProvider,
    FliggyHotelProvider,
    HotelSearchQuery,
    HotelService,
    HotelStayRequest,
)


class _UnavailableProvider:
    provider_name = "unavailable"

    def search_candidates(self, query):
        raise ServiceConfigError("provider unavailable")

    def quote_offer(self, hotel_id, stay_request):
        raise ServiceConfigError("provider unavailable")


class _FakeAmapService:
    def geocode(self, *, address, city=None):
        return {"primary": {"location": "120.123,30.123", "formatted_address": address}}

    def search_stays_with_filters(
        self,
        *,
        location,
        radius,
        limit,
        min_rating,
        max_budget,
        max_distance_m,
        include_unknown_budget,
        include_unknown_rating,
    ):
        return {
            "items": [
                {
                    "id": "stay-1",
                    "name": "西湖湖畔酒店",
                    "type": "酒店",
                    "business_area": "西湖",
                    "address": "西湖大道 1 号",
                    "distance_m": 900,
                    "rating": 4.8,
                    "resolved_price": 580,
                    "price_source": "cost",
                    "tel": "0571-12345678",
                    "location": "120.1,30.2",
                }
            ]
        }


class _FakeFliggyClient:
    pid = "mm_123"

    def call(self, method, **biz_params):
        if method == "taobao.xhotel.city.get":
            return {"cities": [{"city_code": "330100", "city_name": "杭州"}]}
        if method == "taobao.xhotel.info.list.get":
            return {
                "hotels": [
                    {
                        "shid": "1001",
                        "name": "西湖湖畔酒店",
                        "district": "西湖",
                        "address": "西湖大道 1 号",
                        "rating": "4.8",
                        "tel": "0571-12345678",
                        "longitude": "120.1",
                        "latitude": "30.2",
                        "h5_detail_url": "https://example.com/detail",
                    }
                ]
            }
        if method == "taobao.xhotel.price.get":
            return {
                "rooms": [
                    {
                        "room_name": "高级大床房",
                        "sale_price": "688",
                        "cancel_desc": "可免费取消",
                        "h5_booking_url": "https://example.com/book",
                    }
                ]
            }
        raise AssertionError(f"unexpected method: {method}")

    def build_affiliate_url(self, detail_url):
        if not detail_url:
            return None
        return f"{detail_url}?pid={self.pid}"


class HotelServiceTests(unittest.TestCase):
    def test_hotel_service_falls_back_to_amap_provider(self):
        fake_amap = _FakeAmapService()
        service = HotelService(
            providers=[
                _UnavailableProvider(),
                AmapStayFallbackProvider(fake_amap),
            ],
            amap_service=fake_amap,
        )

        result = service.search_candidates(
            destination="杭州",
            center="西湖",
            city="杭州",
            radius=5000,
            limit=5,
        )

        self.assertEqual("amap_fallback", result.provider)
        self.assertEqual("reference", result.price_status)
        self.assertTrue(result.fallback_used)
        self.assertEqual("西湖湖畔酒店", result.candidates[0].name)
        self.assertEqual("amap_cost", result.candidates[0].price_source)
        self.assertIn("美团", " ".join(result.notes))

    def test_fliggy_provider_merges_official_price_with_amap_seed(self):
        fake_amap = _FakeAmapService()
        provider = FliggyHotelProvider(
            amap_service=fake_amap,
            client=_FakeFliggyClient(),
        )

        result = provider.search_candidates(
            HotelSearchQuery(
                destination="杭州",
                center="120.123,30.123",
                city="杭州",
                radius=5000,
                limit=3,
                checkin_date="2026-05-01",
                checkout_date="2026-05-02",
            )
        )

        self.assertEqual("fliggy", result.provider)
        self.assertEqual("quoted", result.price_status)
        self.assertEqual("1001:330100", result.candidates[0].id)
        self.assertEqual("西湖湖畔酒店", result.candidates[0].name)
        self.assertEqual("fliggy_search", result.candidates[0].price_source)
        self.assertEqual("688 元/晚起", result.candidates[0].price_text)
        self.assertIn("book?pid=mm_123", result.candidates[0].booking_url)
        self.assertIn("飞猪价格与房态请以下单页", " ".join(result.notes))

    def test_fliggy_quote_offer_returns_reference_when_city_code_missing(self):
        provider = FliggyHotelProvider(
            amap_service=_FakeAmapService(),
            client=_FakeFliggyClient(),
        )

        quote = provider.quote_offer(
            hotel_id="1001",
            stay_request=HotelStayRequest(checkin_date="2026-05-01", checkout_date="2026-05-02"),
        )

        self.assertEqual("reference_only", quote.status)
        self.assertIn("city_code", " ".join(quote.notes))


if __name__ == "__main__":
    unittest.main()
