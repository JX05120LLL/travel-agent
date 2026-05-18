import unittest
from unittest.mock import MagicMock

from services.providers.amap_service import AmapService
from services.core.errors import ServiceValidationError


class AmapServiceTests(unittest.TestCase):
    def test_geocode_returns_primary_item(self):
        client = MagicMock()
        client.geocode.return_value = {
            "status": "1",
            "count": "1",
            "geocodes": [
                {
                    "formatted_address": "娴欐睙鐪佹澀宸炲競瑗挎箹鍖鸿タ婀栭鏅悕鑳滃尯",
                    "province": "娴欐睙鐪?,
                    "city": "鏉窞甯?,
                    "district": "瑗挎箹鍖?,
                    "adcode": "330106",
                    "location": "120.130663,30.240018",
                    "level": "鍏磋叮鐐?,
                }
            ],
        }
        service = AmapService(client=client)

        payload = service.geocode(address="鏉窞瑗挎箹", city="鏉窞")

        self.assertEqual(1, payload["count"])
        self.assertEqual("鏉窞瑗挎箹", payload["query"]["address"])
        self.assertEqual("120.130663,30.240018", payload["primary"]["location"])

    def test_search_poi_rejects_invalid_page_size(self):
        service = AmapService(client=MagicMock())
        with self.assertRaises(ServiceValidationError):
            service.search_poi(keywords="鐏攨", page_size=30)

    def test_route_transit_requires_city(self):
        service = AmapService(client=MagicMock())
        with self.assertRaises(ServiceValidationError):
            service.route_transit(
                origin="120.130663,30.240018",
                destination="120.153576,30.287459",
                city="",
            )

    def test_route_transit_normalizes_segment_steps(self):
        client = MagicMock()
        client.route_transit.return_value = {
            "route": {
                "transits": [
                    {
                        "distance": "2300",
                        "duration": "1560",
                        "walking_distance": "750",
                        "cost": "3",
                        "segments": [
                            {
                                "walking": {
                                    "distance": "300",
                                    "duration": "240",
                                    "steps": [
                                        {
                                            "instruction": "鍚戜笢姝ヨ 300 绫?,
                                            "assistant_action": "榫欑繑妗ョ珯",
                                        }
                                    ],
                                },
                                "bus": {
                                    "buslines": [
                                        {
                                            "name": "鍦伴搧 1 鍙风嚎(婀樻箹-钀у北鍥介檯鏈哄満)",
                                            "type": "鍦伴搧绾胯矾",
                                            "departure_stop": {"name": "榫欑繑妗ョ珯"},
                                            "arrival_stop": {"name": "瀹氬畨璺珯"},
                                            "via_num": "2",
                                            "distance": "1800",
                                            "duration": "480",
                                        }
                                    ]
                                },
                            },
                            {
                                "walking": {
                                    "distance": "450",
                                    "duration": "420",
                                    "steps": [
                                        {
                                            "instruction": "鍑虹珯鍚庢琛?450 绫冲埌娌冲潑琛?,
                                            "assistant_action": "娌冲潑琛?,
                                        }
                                    ],
                                }
                            },
                        ],
                    }
                ]
            }
        }
        service = AmapService(client=client)

        payload = service.route_transit(
            origin="120.130663,30.240018",
            destination="120.170000,30.250000",
            city="鏉窞",
        )

        primary = payload["primary_transit"]
        self.assertEqual("3 鍏?, primary["cost_text"])
        self.assertEqual(0, primary["transfer_count"])
        self.assertEqual(3, len(primary["steps"]))
        self.assertEqual("walk", primary["steps"][0]["type"])
        self.assertEqual("metro", primary["steps"][1]["type"])
        self.assertEqual("鍦伴搧 1 鍙风嚎", primary["steps"][1]["line"])
        self.assertEqual("榫欑繑妗ョ珯", primary["steps"][1]["departure_stop"])
        self.assertEqual("瀹氬畨璺珯", primary["steps"][1]["arrival_stop"])
        self.assertEqual("娌冲潑琛?, primary["steps"][2]["destination_name"])

    def test_weather_rejects_invalid_extensions(self):
        service = AmapService(client=MagicMock())
        with self.assertRaises(ServiceValidationError):
            service.weather(city="鏉窞", extensions="weekly")

    def test_extract_structured_context_parses_route_and_stay_cards(self):
        structured = AmapService.extract_structured_context(
            [
                "\n".join(
                    [
                        "## 璺嚎瑙勫垝",
                        "- 璧风偣锛氭澀宸炰笢绔?,
                        "- 缁堢偣锛氳タ婀?,
                        "- 鍑鸿鏂瑰紡锛氶┚杞?,
                        "璺濈锛?.2 km",
                        "棰勮鑰楁椂锛?4鍒嗛挓",
                        "鎵撹溅鍙傝€冧环锛?2 鍏?,
                        "",
                        "### 閫愭鎹箻",
                        "1. 姝ヨ 300 绫冲埌缃戠害杞︿笂杞︾偣",
                        "   - 绫诲瀷锛氭琛?,
                        "   - 璺濈锛?00 绫?,
                    ]
                ),
                "\n".join(
                    [
                        "## 浣忓鎺ㄨ崘锛堥厭搴?姘戝锛?,
                        "- 涓績鐐癸細瑗挎箹",
                        "- 鎼滅储鍗婂緞锛?000 绫?,
                        "- 绛涢€夊悗鏁伴噺锛?/6",
                        "- 绛涢€夋潯浠讹細棰勭畻鈮?00 鍏冿紝璇勫垎鈮?.5锛岃窛绂烩墹3000 绫?,
                        "",
                        "### 鎺ㄨ崘鍒楄〃",
                        "1. **婀栫晹閰掑簵**锛堥厭搴楋級",
                        "   璺濈锛?00 m锝滆瘎鍒嗭細4.8锝滀汉鍧囷細380 鍏?,
                        "   鍦板潃锛氳タ婀栧ぇ閬?1 鍙凤綔鐢佃瘽锛?571-12345678",
                        "   浠锋牸鏉ユ簮锛氫汉鍧囦环",
                    ]
                ),
            ]
        )

        self.assertEqual("amap", structured["provider"])
        self.assertEqual(2, len(structured["cards"]))
        self.assertEqual("route", structured["cards"][0]["type"])
        self.assertEqual("鏉窞涓滅珯", structured["routes"][0]["origin"])
        self.assertEqual("瑗挎箹", structured["routes"][0]["destination"])
        self.assertEqual("32 鍏?, structured["routes"][0]["taxi_cost_text"])
        self.assertEqual("姝ヨ", structured["routes"][0]["steps"][0]["type"])
        self.assertEqual(2, structured["stays"][0]["filtered_count"])
        self.assertEqual("婀栫晹閰掑簵", structured["stays"][0]["items"][0]["name"])
        self.assertEqual("380 鍏?, structured["stays"][0]["items"][0]["budget_text"])
        self.assertEqual("浜哄潎浠?, structured["stays"][0]["items"][0]["price_source"])

    def test_extract_structured_context_parses_spot_route_legs(self):
        structured = AmapService.extract_structured_context(
            [
                "\n".join(
                    [
                        "## 鏅偣涓茶仈璺嚎",
                        "- 鍩庡競锛氭澀宸?,
                        "- 鍑鸿鏂瑰紡锛氬叕浜?鍦伴搧",
                        "- 鏅偣椤哄簭锛氳タ婀?-> 娌冲潑琛?-> 鍗楀畫寰¤",
                        "- 鍘熷椤哄簭锛氳タ婀?-> 鍗楀畫寰¤ -> 娌冲潑琛?,
                        "- 鑷姩椤哄簭浼樺寲锛氬凡鍚敤锛堝浐瀹氶鐐癸細瑗挎箹锛?,
                        "",
                        "### 鍒嗘鏄庣粏",
                        "| 娈佃惤 | 璧风偣 | 缁堢偣 | 璺濈 | 鑰楁椂 |",
                        "| --- | --- | --- | --- | --- |",
                        "| 1 | 瑗挎箹 | 娌冲潑琛?| 2.3 km | 24鍒嗛挓 |",
                        "| 2 | 娌冲潑琛?| 鍗楀畫寰¤ | 800 m | 12鍒嗛挓 |",
                        "",
                        "### 绗?1 娈碉細瑗挎箹 -> 娌冲潑琛?,
                        "- 鍑鸿鏂瑰紡锛氬叕浜?鍦伴搧",
                        "- 璺濈锛?.3 km",
                        "- 鑰楁椂锛?4鍒嗛挓",
                        "- 绁ㄤ环鍙傝€冿細3 鍏?,
                        "- 鎬绘琛岃窛绂伙細450 绫?,
                        "1. 姝ヨ 300 绫冲埌榫欑繑妗ョ珯",
                        "   - 绫诲瀷锛氭琛?,
                        "   - 璺濈锛?00 绫?,
                        "   - 鍒拌揪鐐癸細榫欑繑妗ョ珯",
                        "2. 涔樺潗 鍦伴搧1鍙风嚎锛屼粠榫欑繑妗ョ珯鍒板畾瀹夎矾绔欙紝缁忚繃 2 绔?,
                        "   - 绫诲瀷锛氬湴閾?,
                        "   - 绾胯矾锛氬湴閾?鍙风嚎",
                        "   - 涓婅溅绔欙細榫欑繑妗ョ珯",
                        "   - 涓嬭溅绔欙細瀹氬畨璺珯",
                        "   - 绔欐暟锛?",
                        "3. 姝ヨ 150 绫冲埌娌冲潑琛?,
                        "   - 绫诲瀷锛氭琛?,
                        "   - 璺濈锛?50 绫?,
                        "   - 鍒拌揪鐐癸細娌冲潑琛?,
                        "",
                        "### 绗?2 娈碉細娌冲潑琛?-> 鍗楀畫寰¤",
                        "- 鍑鸿鏂瑰紡锛氭琛?,
                        "- 璺濈锛?00 m",
                        "- 鑰楁椂锛?2鍒嗛挓",
                        "1. 姝ヨ 800 绫冲埌鍗楀畫寰¤",
                        "   - 绫诲瀷锛氭琛?,
                        "   - 璺濈锛?00 绫?,
                        "   - 鍒拌揪鐐癸細鍗楀畫寰¤",
                        "",
                        "### 鎬讳綋浼扮畻",
                        "- 鎬昏窛绂伙細3.1 km",
                        "- 鎬昏€楁椂锛?6鍒嗛挓",
                        "- 璇存槑锛氳繖鏄垎娈甸€氬嫟鎬诲拰锛屾湭鍖呭惈鏅偣鍋滅暀鏃堕棿銆?,
                    ]
                )
            ]
        )

        self.assertEqual(1, len(structured["routes"]))
        route = structured["routes"][0]
        self.assertEqual("spot_sequence", route["route_kind"])
        self.assertEqual(["瑗挎箹", "娌冲潑琛?, "鍗楀畫寰¤"], route["spot_sequence"])
        self.assertEqual(["瑗挎箹", "鍗楀畫寰¤", "娌冲潑琛?], route["original_spot_sequence"])
        self.assertEqual("宸插惎鐢紙鍥哄畾棣栫偣锛氳タ婀栵級", route["optimization_note"])
        self.assertEqual(2, len(route["legs"]))
        self.assertEqual("娌冲潑琛?, route["legs"][0]["destination"])
        self.assertEqual("3 鍏?, route["legs"][0]["ticket_cost_text"])
        self.assertEqual("鍦伴搧", route["legs"][0]["steps"][1]["type"])
        self.assertEqual("3.1 km", route["total_distance_text"])


if __name__ == "__main__":
    unittest.main()
