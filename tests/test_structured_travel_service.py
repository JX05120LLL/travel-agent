import sys
import types
import unittest
import uuid
import json
from types import SimpleNamespace

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    httpx_module.get = object
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

from services.travel.structured_travel_service import StructuredTravelService


class StructuredTravelServiceTests(unittest.TestCase):
    def test_build_from_message_merges_railway_budget_notes_and_assumptions(self):
        message = SimpleNamespace(
            id=uuid.uuid4(),
            content="\n".join(
                [
                    "## 鎺ㄨ崘鏂规",
                    "### 鎺ㄨ崘鐞嗙敱",
                    "- 浜ら€氳鎺ユ洿椤?,
                    "- 浣忓鐗囧尯鏇撮€傚悎杞绘澗娓?,
                    "### 棰勭畻姹囨€?,
                    "- 浜哄潎绾?1200-1600 鍏冿紝鍖呭惈閰掑簵涓庡競鍐呬氦閫?,
                    "- 閰掑簵棰勭畻锛?00-700 鍏?鏅?,
                    "- 椁愰ギ棰勭畻锛?50-250 鍏?澶?,
                    "### 娉ㄦ剰浜嬮」",
                    "- 浜斾竴鏈熼棿鐑棬鏅偣寤鸿鎻愬墠棰勭害",
                    "- 鏅氶棿杩旂▼灏介噺閬垮紑鏈彮杞﹀墠楂樺嘲",
                    "### 鏈鍋囪",
                    "- 榛樿浠庝笂娴峰嚭鍙?,
                    "- 榛樿涓ゅぉ涓€鏅氳交鏉炬父",
                ]
            ),
            message_metadata={
                "tool_outputs": [
                    "\n".join(
                        [
                            "## 璺ㄥ煄鍒拌揪寤鸿锛?2306锛?,
                            "- 鍑哄彂鍩庡競锛氫笂娴?,
                            "- 鐩殑鍩庡競锛氭澀宸?,
                            "- 鍑哄彂鏃ユ湡锛?026-05-01",
                            "- 鎺ㄨ崘鏂瑰紡锛氶珮閾?鍔ㄨ溅锛堝緟纭杞︽锛?,
                            "- 棰勮鑰楁椂锛?灏忔椂08鍒嗛挓",
                            "- 绁ㄤ环鍙傝€冿細73 鍏冭捣",
                            "- 鎺ュ叆鐘舵€侊細placeholder",
                            "- 绁ㄥ姟鐘舵€侊細reference",
                            "- 鏁版嵁鏉ユ簮锛歱laceholder",
                            "- 鏂规鎽樿锛氬缓璁紭鍏堥珮閾佸埌杈炬澀宸炰笢绔欙紝鍐嶈鎺ヨタ婀栫墖鍖洪厭搴椼€?,
                            "",
                            "### 鎺ㄨ崘杞︽",
                            "1. G7311",
                            "   - 绔欑偣锛氫笂娴疯櫣妗?-> 鏉窞涓?,
                            "   - 淇℃伅锛?7:00锝?8:08锝?灏忔椂08鍒嗛挓锝?3 鍏冭捣",
                            "",
                            "### 瀹樻柟璐エ鎻愰啋",
                            "- 娓犻亾锛氶搧璺?2306瀹樻柟",
                            "- 瀹樼綉锛歨ttps://www.12306.cn/",
                            "- App锛歨ttps://kyfw.12306.cn/otn/appDownload/init",
                            "- 鎻愰啋锛氳溅娆°€佺エ浠枫€佷綑绁ㄤ笌璐エ瑙勫垯璇蜂互閾佽矾12306瀹樼綉/App涓哄噯銆?,
                            "",
                            "### 琛ュ厖璇存槑",
                            "- 褰撳墠杞︽浠呬綔鏌ヨ鍙傝€冿紝璇峰墠寰€閾佽矾12306瀹樻柟瀹屾垚璐エ銆?,
                        ]
                    ),
                    "\n".join(
                        [
                            "## 閰掑簵姘戝鎺ㄨ崘锛堜緵搴斿晢鑱氬悎锛?,
                            "- 鐩殑鍦帮細鏉窞",
                            "- 涓績鐐癸細瑗挎箹",
                            "- 鎼滅储鍗婂緞锛?000 绫?,
                            "- 鎺ㄨ崘鏉ユ簮锛歛map_fallback",
                            "- 浠锋牸鐘舵€侊細reference",
                            "- 鍏ヤ綇鏃ユ湡锛?026-05-01",
                            "- 绂诲簵鏃ユ湡锛?026-05-02",
                            "",
                            "### 鎺ㄨ崘鍒楄〃",
                            "1. **婀栫晹閰掑簵**锛堥厭搴楋級",
                            "   - 鐗囧尯锛氳タ婀?,
                            "   - 璺濈锛?00 m",
                            "   - 璇勫垎锛?.8",
                            "   - 浠锋牸锛?80 鍏?鏅氳捣",
                            "   - 浠锋牸鏉ユ簮锛歛map_cost",
                            "   - 鏄惁瀹炴椂浠凤細鍚?,
                            "   - 鍦板潃锛氳タ婀栧ぇ閬?1 鍙?,
                            "",
                            "### 棰勮鎻愰啋",
                            "- 浠锋牸涓庢埧鎬佽浠ヤ笅鍗曢〉涓哄噯銆?,
                        ]
                    )
                ]
            },
        )

        structured = StructuredTravelService.build_from_message(message)

        self.assertIn("railway12306", structured)
        self.assertIn("hotel_accommodation", structured)
        self.assertIn("assistant_plan", structured)
        self.assertEqual("arrival_recommendation", structured["railway12306"]["cards"][0]["type"])
        self.assertEqual("涓婃捣", structured["railway12306"]["arrivals"][0]["origin_city"])
        self.assertEqual(
            "楂橀搧/鍔ㄨ溅锛堝緟纭杞︽锛?,
            structured["railway12306"]["arrivals"][0]["recommended_mode"],
        )
        self.assertEqual("閾佽矾12306瀹樻柟", structured["railway12306"]["arrivals"][0]["official_notice"]["娓犻亾"])
        hotel_search = structured["hotel_accommodation"]["searches"][0]
        self.assertEqual("鏉窞", hotel_search["destination"])
        self.assertEqual("amap_fallback", hotel_search["provider"])
        self.assertEqual("amap_cost", hotel_search["items"][0]["浠锋牸鏉ユ簮"])
        self.assertEqual("budget_summary", structured["assistant_plan"]["cards"][0]["type"])
        self.assertEqual(
            "浜哄潎绾?1200-1600 鍏冿紝鍖呭惈閰掑簵涓庡競鍐呬氦閫?,
            structured["assistant_plan"]["budget"]["summary"],
        )
        self.assertEqual(2, len(structured["assistant_plan"]["reasons"]["items"]))
        self.assertEqual(2, len(structured["assistant_plan"]["notes"]["items"]))
        self.assertEqual(2, len(structured["assistant_plan"]["assumptions"]["items"]))
        self.assertEqual(
            str(message.id),
            structured["assistant_plan"]["source_message_id"],
        )

    def test_extracts_amap_map_preview_payload(self):
        preview_payload = {
            "provider_mode": "mcp",
            "title": "鏉窞琛岀▼鍦板浘",
            "city": "鏉窞",
            "center": "120.143222,30.236064",
            "markers": [
                {"name": "鏉窞涓滅珯", "location": "120.219375,30.291225"},
                {"name": "瑗挎箹", "location": "120.143222,30.236064"},
            ],
            "official_map_url": "https://uri.amap.com/marker?position=120.143222,30.236064",
        }
        structured = StructuredTravelService.extract_structured_context(
            tool_outputs=[
                "## 楂樺痉鍦板浘棰勮\n"
                f"MAP_PREVIEW_JSON: {json.dumps(preview_payload, ensure_ascii=False)}"
            ],
            content=None,
        )

        self.assertIn("amap", structured)
        self.assertEqual("鏉窞琛岀▼鍦板浘", structured["amap"]["map_preview"]["title"])
        self.assertEqual("map_preview", structured["amap"]["cards"][-1]["type"])


if __name__ == "__main__":
    unittest.main()
