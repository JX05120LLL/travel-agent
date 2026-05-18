import unittest
from types import SimpleNamespace

from services.travel.trip_document_service import TripDocumentService


class TripDocumentServiceTests(unittest.TestCase):
    def test_builds_delivery_payload_and_markdown(self):
        trip = SimpleNamespace(
            title="鏉窞涓ゅぉ杞绘澗娓?,
            summary="鍖呭惈楂橀搧銆侀厭搴椼€佹櫙鐐逛笌缇庨鐨勪竴鏉￠緳琛岀▼銆?,
            primary_destination="鏉窞",
            total_days=2,
            status="confirmed",
            itinerary_days=[
                SimpleNamespace(
                    day_no=1,
                    title="绗?1 澶╁畨鎺?,
                    city_name="鏉窞",
                    summary="褰撴棩鏅偣鍔ㄧ嚎锛氳タ婀?-> 娌冲潑琛?,
                    items=[
                        {
                            "type": "spot_sequence",
                            "spot_sequence": ["瑗挎箹", "娌冲潑琛?],
                            "optimization_note": "宸插惎鐢ㄥ浐瀹氶鐐逛紭鍖?,
                            "time_period": "morning",
                        },
                        {
                            "type": "transit",
                            "from": "瑗挎箹",
                            "to": "娌冲潑琛?,
                            "mode": "鍏氦/鍦伴搧",
                            "distance_text": "2.3 km",
                            "duration_text": "24鍒嗛挓",
                            "ticket_cost_text": "3 鍏?,
                            "route_kind": "spot_leg",
                            "step_details": [
                                {
                                    "instruction": "涔樺潗 鍦伴搧1鍙风嚎锛屼粠榫欑繑妗ョ珯鍒板畾瀹夎矾绔?,
                                    "line": "鍦伴搧1鍙风嚎",
                                    "departure_stop": "榫欑繑妗ョ珯",
                                    "arrival_stop": "瀹氬畨璺珯",
                                }
                            ],
                            "time_period": "afternoon",
                        },
                        {
                            "type": "food_recommendations",
                            "items": [{"name": "鐭ュ懗瑙?}],
                            "time_period": "evening",
                        },
                    ],
                )
            ],
        )
        structured_context = {
            "railway12306": {
                "arrivals": [
                    {
                        "origin_city": "涓婃捣",
                        "destination_city": "鏉窞",
                        "recommended_mode": "楂橀搧/鍔ㄨ溅",
                        "duration_text": "1灏忔椂08鍒嗛挓",
                        "price_text": "73 鍏冭捣",
                        "summary": "浼樺厛楂橀搧鍒拌揪鏉窞涓滅珯銆?,
                        "ticket_status": "reference",
                        "data_source": "placeholder",
                        "official_notice": {"notice": "璇蜂互閾佽矾12306瀹樼綉/App涓哄噯銆?},
                        "candidates": [{"train_no": "G7311", "depart_station": "涓婃捣铏规ˉ", "arrive_station": "鏉窞涓?}],
                    }
                ]
            },
            "amap": {
                "routes": [
                    {
                        "route_kind": "point_to_point",
                        "origin": "鏉窞涓滅珯",
                        "destination": "婀栫晹閰掑簵",
                        "mode": "鍦伴搧/姝ヨ",
                        "distance_text": "8.4 km",
                        "duration_text": "32鍒嗛挓",
                        "ticket_cost_text": "4 鍏?,
                        "steps": [
                            {
                                "instruction": "浠庢澀宸炰笢绔欎箻鍦伴搧 1 鍙风嚎鍓嶅線榫欑繑妗ョ珯銆?,
                                "line": "鍦伴搧 1 鍙风嚎",
                                "departure_stop": "鏉窞涓滅珯",
                                "arrival_stop": "榫欑繑妗ョ珯",
                            },
                            {
                                "instruction": "鍑虹珯鍚庢琛岀害 600 绫冲埌杈炬箹鐣旈厭搴椼€?,
                                "distance_text": "600 绫?,
                                "duration_text": "9 鍒嗛挓",
                            },
                        ],
                    }
                ],
                "map_preview": {
                    "provider_mode": "mcp",
                    "title": "鏉窞涓ゅぉ鍦板浘棰勮",
                    "city": "鏉窞",
                    "center": "120.143222,30.236064",
                    "markers": [
                        {"name": "鏉窞涓滅珯", "location": "120.219375,30.291225"},
                        {"name": "瑗挎箹", "location": "120.143222,30.236064"},
                    ],
                    "personal_map_url": "https://example.com/personal-map",
                    "personal_map_open_url": "https://example.com/personal-map",
                    "official_map_url": "https://uri.amap.com/marker?position=120.143222,30.236064",
                    "navigation_url": "https://uri.amap.com/navigation?from=foo&to=bar",
                    "fetched_at": "2026-04-25T10:00:00Z",
                }
            },
            "hotel_accommodation": {
                "searches": [
                    {
                        "summary": "婀栫晹閰掑簵锛?80 鍏?鏅氳捣锛宎map_cost锛岃タ婀?,
                        "price_status": "reference",
                        "items": [
                            {
                                "name": "婀栫晹閰掑簵",
                                "鐗囧尯": "瑗挎箹",
                                "浠锋牸": "580 鍏?鏅氳捣",
                                "浠锋牸鏉ユ簮": "amap_cost",
                            }
                        ],
                        "notes": ["浠锋牸涓庢埧鎬佽浠ヤ笅鍗曢〉涓哄噯銆?],
                    }
                ]
            },
            "assistant_plan": {
                "budget": {"summary": "浜哄潎绾?1500-1900 鍏?, "items": ["閰掑簵 580 鍏?鏅?]},
                "notes": {"summary": "宸叉暣鐞嗗嚭琛屾敞鎰忎簨椤?, "items": ["浜斾竴闇€鎻愬墠棰勭害鐑棬鏅偣"]},
                "assumptions": {"summary": "鏈疆瑙勫垝浣跨敤浜嗛粯璁ゅ亣璁?, "items": ["榛樿涓ゅぉ涓€鏅?]},
                "reasons": {"summary": "宸叉暣鐞嗘湰娆℃帹鑽愮悊鐢?, "items": ["浜ら€氳鎺ユ洿椤?]},
            },
        }

        payload = TripDocumentService.build_delivery_payload(trip=trip, structured_context=structured_context)
        markdown = TripDocumentService.build_document_markdown(payload)
        confidence = TripDocumentService.build_price_confidence_summary(payload)

        self.assertEqual("鏉窞涓ゅぉ杞绘澗娓?, payload["overview"]["title"])
        self.assertEqual("reference", payload["stay"]["price_status"])
        self.assertEqual("reference", confidence["rail_ticket_status"])
        self.assertEqual("arrival", payload["daily_itinerary"][0]["day_type"])
        self.assertEqual("Day 0 鍒拌揪鏃?, payload["daily_itinerary"][0]["title"])
        self.assertIn("transfer_to_stay_or_first_stop", payload["daily_itinerary"][0])
        self.assertIn(
            "鍦伴搧/姝ヨ",
            payload["daily_itinerary"][0]["transfer_to_stay_or_first_stop"]["transport"],
        )
        self.assertEqual("鏉窞涓ゅぉ鍦板浘棰勮", payload["map_preview"]["title"])
        self.assertIn("閰掑簵鎺ㄨ崘", markdown)
        self.assertIn("鍒拌揪鏂瑰紡", markdown)
        self.assertIn("鍦板浘瀵艰埅", markdown)
        self.assertIn("姣忔棩琛岀▼", markdown)
        self.assertIn("Day 0 鍒拌揪鏃?, markdown)
        self.assertIn("鐭ュ懗瑙?, markdown)
        self.assertIn("璺ㄥ煄鎶佃揪", markdown)
        self.assertIn("鍒扮珯鍚庡幓閰掑簵/棣栨櫙鐐?, markdown)
        self.assertIn("涓撳睘鍦板浘", markdown)
        self.assertNotIn("| --- |", markdown)

    def test_placeholder_arrival_marks_missing_real_train(self):
        trip = SimpleNamespace(
            title="鏉窞鍛ㄦ湯娓?,
            summary="鍏堥獙璇佸埌杈炬棩鍗犱綅鏂囨銆?,
            primary_destination="鏉窞",
            total_days=1,
            status="draft",
            itinerary_days=[],
        )
        structured_context = {
            "railway12306": {
                "arrivals": [
                    {
                        "origin_city": "涓婃捣",
                        "destination_city": "鏉窞",
                        "recommended_mode": "楂橀搧/鍔ㄨ溅锛堝緟纭杞︽锛?,
                        "duration_text": "寰呮帴鍏ュ疄鏃惰溅娆″悗琛ュ厖",
                        "price_text": "寰呮帴鍏ュ疄鏃剁エ浠峰悗琛ュ厖",
                        "summary": "",
                        "ticket_status": "placeholder",
                        "data_source": "placeholder",
                        "official_notice": {"notice": "杞︽銆佺エ浠枫€佷綑绁ㄤ笌璐エ瑙勫垯璇蜂互閾佽矾12306瀹樼綉/App涓哄噯銆?},
                        "candidates": [],
                    }
                ]
            }
        }

        payload = TripDocumentService.build_delivery_payload(trip=trip, structured_context=structured_context)

        self.assertEqual("arrival", payload["daily_itinerary"][0]["day_type"])
        self.assertIn("鏆傛湭鑾峰彇鍒扮湡瀹炶溅娆?, payload["daily_itinerary"][0]["summary"])
        self.assertIn(
            "鏆傛湭鑾峰彇鍒扮湡瀹炶溅娆?,
            payload["daily_itinerary"][0]["periods"][0]["blocks"][0]["note"],
        )
        self.assertIn(
            "鏆傛湭鑾峰彇鍒扮珯鍚庣粏璺嚎",
            payload["daily_itinerary"][0]["transfer_to_stay_or_first_stop"]["note"],
        )


if __name__ == "__main__":
    unittest.main()
