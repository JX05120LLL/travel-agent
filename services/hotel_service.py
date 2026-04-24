"""酒店/民宿聚合服务。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from services.amap_service import AmapService
from services.errors import (
    ServiceConfigError,
    ServiceIntegrationError,
    ServiceValidationError,
)
from services.external_call_guard import ExternalCallPolicy, external_call_guard


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", []):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", []):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_price_source(source: str | None) -> str:
    mapping = {
        "lowest_price": "飞猪搜索价",
        "cost": "高德均价",
        "amap_cost": "高德均价",
        "amap_lowest_price": "高德最低价",
        "fliggy_live": "飞猪实时价",
        "fliggy_search": "飞猪搜索价",
        "fliggy_reference": "飞猪可解析报价",
        "fliggy_ai": "飞猪搜索价",
        "unknown": "未标注",
    }
    key = (source or "").strip().lower()
    return mapping.get(key, source or "未标注")


def _normalize_hotel_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[（）()·,，.\-_/\\\s]", "", text)
    for token in ("酒店", "宾馆", "民宿", "公寓", "客栈", "hotel", "hotels", "inn"):
        text = text.replace(token, "")
    return text


def _normalize_city_name(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("市", "地区", "自治州", "盟", "特别行政区"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def _iter_nested_dicts(payload: Any):
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from _iter_nested_dicts(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_nested_dicts(item)


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


@dataclass(slots=True)
class HotelSearchQuery:
    destination: str
    center: str
    city: str = ""
    radius: int = 5000
    limit: int = 6
    max_budget: float | None = None
    min_rating: float | None = None
    max_distance_m: int | None = None
    checkin_date: str = ""
    checkout_date: str = ""


@dataclass(slots=True)
class HotelStayRequest:
    checkin_date: str = ""
    checkout_date: str = ""
    rooms: int = 1
    adults: int = 2


@dataclass(slots=True)
class HotelCandidate:
    id: str | None
    name: str
    stay_type: str
    district: str | None = None
    address: str | None = None
    distance_text: str | None = None
    distance_m: int | None = None
    rating: float | None = None
    price: float | None = None
    price_text: str | None = None
    price_source: str | None = None
    is_live_price: bool = False
    room_summary: str | None = None
    provider: str = "unknown"
    booking_url: str | None = None
    tel: str | None = None
    location: str | None = None
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["price_source_label"] = _normalize_price_source(self.price_source)
        return payload


@dataclass(slots=True)
class HotelSearchResult:
    provider: str
    provider_mode: str
    status: str
    price_status: str
    center: str
    destination: str
    city: str = ""
    radius: int = 5000
    candidates: list[HotelCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fallback_used: bool = False
    fetched_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_mode": self.provider_mode,
            "status": self.status,
            "price_status": self.price_status,
            "center": self.center,
            "destination": self.destination,
            "city": self.city,
            "radius": self.radius,
            "candidates": [item.to_dict() for item in self.candidates],
            "notes": list(self.notes),
            "fallback_used": self.fallback_used,
            "fetched_at": self.fetched_at,
        }


@dataclass(slots=True)
class HotelQuoteResult:
    provider: str
    hotel_id: str
    status: str
    price: float | None = None
    price_text: str | None = None
    price_source: str | None = None
    room_summary: str | None = None
    booking_url: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "hotel_id": self.hotel_id,
            "status": self.status,
            "price": self.price,
            "price_text": self.price_text,
            "price_source": self.price_source,
            "price_source_label": _normalize_price_source(self.price_source),
            "room_summary": self.room_summary,
            "booking_url": self.booking_url,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class FliggyHotelRecord:
    shid: str
    city_code: str
    name: str
    district: str | None = None
    address: str | None = None
    rating: float | None = None
    tel: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    detail_url: str | None = None
    h5_detail_url: str | None = None
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        return f"{self.shid}:{self.city_code}"

    @property
    def location(self) -> str | None:
        if self.longitude and self.latitude:
            return f"{self.longitude},{self.latitude}"
        return None


@dataclass(slots=True)
class FliggyQuotePayload:
    price: float | None = None
    price_text: str | None = None
    booking_url: str | None = None
    room_summary: str | None = None
    price_source: str = "fliggy_search"
    is_live_price: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


class HotelProvider(Protocol):
    provider_name: str

    def search_candidates(self, query: HotelSearchQuery) -> HotelSearchResult:
        ...

    def quote_offer(self, hotel_id: str, stay_request: HotelStayRequest) -> HotelQuoteResult:
        ...


class FliggyTopClient:
    """飞猪 TOP API 客户端。"""

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        base_url: str = "",
        timeout_seconds: float = 12,
        pid: str = "",
        partner_id: str = "travel-agent",
        sign_method: str = "md5",
    ) -> None:
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.base_url = (base_url or "").strip() or "https://eco.taobao.com/router/rest"
        self.timeout_seconds = timeout_seconds
        self.pid = (pid or "").strip()
        self.partner_id = partner_id
        self.sign_method = (sign_method or "md5").strip().lower()
        if self.sign_method != "md5":
            raise ServiceConfigError("当前仅支持飞猪 TOP 的 md5 签名方式。")

    def call(self, method: str, **biz_params: Any) -> dict[str, Any]:
        params: dict[str, str] = {
            "method": method,
            "app_key": self.app_key,
            "format": "json",
            "v": "2.0",
            "sign_method": self.sign_method,
            "simplify": "true",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self.partner_id:
            params["partner_id"] = self.partner_id

        for key, value in biz_params.items():
            if value in (None, ""):
                continue
            if isinstance(value, bool):
                params[key] = "true" if value else "false"
            else:
                params[key] = str(value)

        params["sign"] = self._sign(params)

        try:
            response = httpx.post(
                self.base_url,
                data=params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ServiceIntegrationError("飞猪接口请求超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise ServiceIntegrationError(f"飞猪接口返回错误：{exc.response.status_code}") from exc
        except (ValueError, httpx.HTTPError) as exc:
            raise ServiceIntegrationError(f"飞猪接口调用失败：{exc}") from exc

        error_payload = payload.get("error_response")
        if error_payload:
            sub_msg = _first_non_empty(
                error_payload.get("sub_msg"),
                error_payload.get("msg"),
                error_payload.get("sub_code"),
            )
            raise ServiceIntegrationError(f"飞猪接口业务错误：{sub_msg or '未知错误'}")

        response_key = f"{method.replace('.', '_')}_response"
        if response_key in payload and isinstance(payload[response_key], dict):
            return payload[response_key]

        dict_values = [item for item in payload.values() if isinstance(item, dict)]
        if len(dict_values) == 1:
            return dict_values[0]
        return payload

    def build_affiliate_url(self, detail_url: str | None) -> str | None:
        if not detail_url:
            return None
        if not self.pid:
            return detail_url
        joiner = "&" if "?" in detail_url else "?"
        return f"{detail_url}{joiner}{urlencode({'pid': self.pid})}"

    def _sign(self, params: dict[str, str]) -> str:
        content = "".join(f"{key}{params[key]}" for key in sorted(params.keys()) if key != "sign")
        digest = hashlib.md5(f"{self.app_secret}{content}{self.app_secret}".encode("utf-8")).hexdigest()
        return digest.upper()


class FliggyHotelProvider:
    """飞猪官方酒店 provider。"""

    provider_name = "fliggy"
    _CITY_METHOD = "taobao.xhotel.city.get"
    _HOTEL_LIST_METHOD = "taobao.xhotel.info.list.get"
    _PRICE_METHOD = "taobao.xhotel.price.get"

    def __init__(
        self,
        amap_service: AmapService | None = None,
        client: FliggyTopClient | None = None,
    ) -> None:
        self.amap_service = amap_service or AmapService()
        self.timeout_seconds = float(os.getenv("FLIGGY_TIMEOUT_SECONDS", "12") or "12")
        self.client = client

    def _ensure_client(self) -> FliggyTopClient:
        if self.client is not None:
            return self.client

        app_key = os.getenv("FLIGGY_APP_KEY", "").strip()
        app_secret = os.getenv("FLIGGY_APP_SECRET", "").strip()
        if not app_key or not app_secret:
            raise ServiceConfigError("飞猪酒店服务未配置，已自动回退到其他住宿来源。")

        self.client = FliggyTopClient(
            app_key=app_key,
            app_secret=app_secret,
            pid=os.getenv("FLIGGY_PID", "").strip(),
            base_url=os.getenv("FLIGGY_BASE_URL", "").strip(),
            timeout_seconds=self.timeout_seconds,
        )
        return self.client

    def search_candidates(self, query: HotelSearchQuery) -> HotelSearchResult:
        client = self._ensure_client()
        city_name = _normalize_city_name(query.city or query.destination)
        if not city_name:
            raise ServiceValidationError("飞猪酒店查询需要 city 或 destination。")

        city_code = self._resolve_city_code(client, city_name)
        geo_seeds = self._search_geo_seed_candidates(query)
        hotel_records = self._list_hotels(client, city_code=city_code, city_name=city_name, seed_items=geo_seeds)
        if not hotel_records:
            return HotelSearchResult(
                provider=self.provider_name,
                provider_mode="api",
                status="empty",
                price_status="missing",
                center=query.center,
                destination=query.destination,
                city=query.city,
                radius=query.radius,
                notes=["飞猪已接入，但当前未匹配到可展示的酒店候选，已回退到其他住宿来源。"],
                fetched_at=_utc_now_iso(),
            )

        quotes: dict[str, FliggyQuotePayload] = {}
        errors: list[str] = []
        if query.checkin_date and query.checkout_date:
            for record in hotel_records[: query.limit]:
                try:
                    quotes[record.candidate_id] = self._fetch_quote(
                        client,
                        shid_city_code=f"{record.shid}_{record.city_code}",
                        stay_request=HotelStayRequest(
                            checkin_date=query.checkin_date,
                            checkout_date=query.checkout_date,
                        ),
                    )
                except ServiceIntegrationError as exc:
                    errors.append(str(exc))

        candidates = [
            self._build_candidate(record=record, quote=quotes.get(record.candidate_id), seed_map=geo_seeds)
            for record in hotel_records[: query.limit]
        ]
        price_status = "quoted" if any(item.price is not None for item in candidates) else "info_only"
        notes = ["飞猪价格与房态请以下单页和供应商实际展示为准。"]
        if not os.getenv("FLIGGY_PID", "").strip():
            notes.append("当前未配置飞猪 PID，预订链接将使用酒店详情页直链。")
        notes.extend(errors)
        return HotelSearchResult(
            provider=self.provider_name,
            provider_mode="api",
            status="ok",
            price_status=price_status,
            center=query.center,
            destination=query.destination,
            city=query.city,
            radius=query.radius,
            candidates=candidates,
            notes=notes,
            fetched_at=_utc_now_iso(),
        )

    def quote_offer(self, hotel_id: str, stay_request: HotelStayRequest) -> HotelQuoteResult:
        client = self._ensure_client()
        shid_city_code = (hotel_id or "").strip().replace(":", "_")
        if "_" not in shid_city_code:
            return HotelQuoteResult(
                provider=self.provider_name,
                hotel_id=hotel_id,
                status="reference_only",
                notes=["当前缺少飞猪 hotel_id 对应的 city_code，暂时无法单独补报价。"],
            )
        if not stay_request.checkin_date or not stay_request.checkout_date:
            return HotelQuoteResult(
                provider=self.provider_name,
                hotel_id=hotel_id,
                status="reference_only",
                notes=["飞猪报价需要 checkin_date 和 checkout_date。"],
            )

        quote = self._fetch_quote(client, shid_city_code=shid_city_code, stay_request=stay_request)
        status = "ok" if quote.price is not None or quote.booking_url else "reference_only"
        return HotelQuoteResult(
            provider=self.provider_name,
            hotel_id=hotel_id,
            status=status,
            price=quote.price,
            price_text=quote.price_text,
            price_source=quote.price_source,
            room_summary=quote.room_summary,
            booking_url=quote.booking_url,
            notes=["飞猪价格与房态请以下单页为准。"],
        )

    def _resolve_city_code(self, client: FliggyTopClient, city_name: str) -> str:
        normalized_target = _normalize_city_name(city_name)
        policy = ExternalCallPolicy(
            provider="fliggy_hotel",
            operation="resolve_city_code",
            ttl_seconds=24 * 60 * 60,
            rate_limit=30,
            rate_window_seconds=60,
            circuit_breaker_threshold=3,
            circuit_open_seconds=60,
        )
        cache_key = normalized_target
        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_resolve_city_code(client, normalized_target),
        )

    def _do_resolve_city_code(self, client: FliggyTopClient, city_name: str) -> str:
        for page_no in range(1, 11):
            raw = client.call(self._CITY_METHOD, page_no=page_no, page_size=100)
            candidates = list(self._extract_city_items(raw))
            if not candidates:
                break
            for item in candidates:
                names = {
                    _normalize_city_name(item.get("city_name")),
                    _normalize_city_name(item.get("name")),
                    _normalize_city_name(item.get("domestic_name")),
                }
                if city_name in names:
                    city_code = _first_non_empty(item.get("city_code"), item.get("code"), item.get("id"))
                    if city_code:
                        return str(city_code)
        raise ServiceIntegrationError(f"飞猪未找到城市编码：{city_name}")

    def _extract_city_items(self, payload: dict[str, Any]):
        for node in _iter_nested_dicts(payload):
            city_code = _first_non_empty(node.get("city_code"), node.get("code"))
            city_name = _first_non_empty(node.get("city_name"), node.get("name"), node.get("domestic_name"))
            if city_code and city_name:
                yield node

    def _search_geo_seed_candidates(self, query: HotelSearchQuery) -> dict[str, dict[str, Any]]:
        result = self.amap_service.search_stays_with_filters(
            location=query.center,
            radius=query.radius,
            limit=max(query.limit * 3, 8),
            min_rating=query.min_rating,
            max_budget=query.max_budget,
            max_distance_m=query.max_distance_m,
            include_unknown_budget=True,
            include_unknown_rating=True,
        )
        seeds: dict[str, dict[str, Any]] = {}
        for item in result.get("items") or []:
            normalized = _normalize_hotel_name(item.get("name"))
            if not normalized:
                continue
            seeds[normalized] = dict(item)
        return seeds

    def _list_hotels(
        self,
        client: FliggyTopClient,
        *,
        city_code: str,
        city_name: str,
        seed_items: dict[str, dict[str, Any]],
    ) -> list[FliggyHotelRecord]:
        page_limit = max(int(os.getenv("FLIGGY_HOTEL_MAX_PAGES", "3") or "3"), 1)
        per_page = max(int(os.getenv("FLIGGY_HOTEL_PAGE_SIZE", "50") or "50"), 20)
        policy = ExternalCallPolicy(
            provider="fliggy_hotel",
            operation="list_hotels",
            ttl_seconds=30 * 60,
            rate_limit=30,
            rate_window_seconds=60,
            circuit_breaker_threshold=4,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps(
            {"city_code": city_code, "city_name": city_name, "seed_names": sorted(seed_items.keys())[:10]},
            ensure_ascii=False,
            sort_keys=True,
        )
        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_list_hotels(
                client,
                city_code=city_code,
                city_name=city_name,
                seed_items=seed_items,
                page_limit=page_limit,
                per_page=per_page,
            ),
        )

    def _do_list_hotels(
        self,
        client: FliggyTopClient,
        *,
        city_code: str,
        city_name: str,
        seed_items: dict[str, dict[str, Any]],
        page_limit: int,
        per_page: int,
    ) -> list[FliggyHotelRecord]:
        records: list[FliggyHotelRecord] = []
        for page_no in range(1, page_limit + 1):
            raw = client.call(
                self._HOTEL_LIST_METHOD,
                city_code=city_code,
                page_no=page_no,
                page_size=per_page,
            )
            page_records = [self._parse_hotel_record(item, city_code) for item in self._extract_hotel_items(raw)]
            page_records = [item for item in page_records if item is not None]
            if not page_records:
                break
            records.extend(page_records)

        if not records:
            return []

        if not seed_items:
            return records[:8]

        scored: list[tuple[float, FliggyHotelRecord]] = []
        for record in records:
            normalized = _normalize_hotel_name(record.name)
            best_score = 0.0
            for seed_name in seed_items.keys():
                score = SequenceMatcher(None, normalized, seed_name).ratio()
                if score > best_score:
                    best_score = score
            if best_score >= 0.42:
                scored.append((best_score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        unique: dict[str, FliggyHotelRecord] = {}
        for _, record in scored:
            unique.setdefault(record.candidate_id, record)
        return list(unique.values()) or records[:8]

    def _extract_hotel_items(self, payload: dict[str, Any]):
        for node in _iter_nested_dicts(payload):
            shid = _first_non_empty(node.get("shid"), node.get("hotel_id"), node.get("hid"))
            name = _first_non_empty(node.get("name"), node.get("hotel_name"), node.get("outer_name"))
            if shid and name:
                yield node

    def _parse_hotel_record(self, item: dict[str, Any], city_code: str) -> FliggyHotelRecord | None:
        shid = _first_non_empty(item.get("shid"), item.get("hotel_id"), item.get("hid"))
        name = _first_non_empty(item.get("name"), item.get("hotel_name"), item.get("outer_name"))
        if not shid or not name:
            return None
        return FliggyHotelRecord(
            shid=str(shid),
            city_code=str(city_code),
            name=str(name),
            district=_first_non_empty(item.get("district"), item.get("business"), item.get("business_area")),
            address=_first_non_empty(item.get("address"), item.get("addr")),
            rating=_safe_float(_first_non_empty(item.get("rating"), item.get("star"), item.get("score"))),
            tel=_first_non_empty(item.get("tel"), item.get("phone"), item.get("telephone")),
            latitude=str(item.get("latitude")) if item.get("latitude") not in (None, "") else None,
            longitude=str(item.get("longitude")) if item.get("longitude") not in (None, "") else None,
            detail_url=_first_non_empty(item.get("detail_url"), item.get("pc_detail_url"), item.get("hotel_url")),
            h5_detail_url=_first_non_empty(item.get("h5_detail_url"), item.get("wireless_url")),
            tags=[str(tag).strip() for tag in item.get("tags") or [] if str(tag).strip()],
            raw=dict(item),
        )

    def _fetch_quote(
        self,
        client: FliggyTopClient,
        *,
        shid_city_code: str,
        stay_request: HotelStayRequest,
    ) -> FliggyQuotePayload:
        policy = ExternalCallPolicy(
            provider="fliggy_hotel",
            operation="quote_offer",
            ttl_seconds=10 * 60,
            rate_limit=50,
            rate_window_seconds=60,
            circuit_breaker_threshold=5,
            circuit_open_seconds=60,
        )
        cache_key = json.dumps(
            {
                "shid_city_code": shid_city_code,
                "checkin_date": stay_request.checkin_date,
                "checkout_date": stay_request.checkout_date,
                "rooms": stay_request.rooms,
                "adults": stay_request.adults,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_fetch_quote(client, shid_city_code=shid_city_code, stay_request=stay_request),
        )

    def _do_fetch_quote(
        self,
        client: FliggyTopClient,
        *,
        shid_city_code: str,
        stay_request: HotelStayRequest,
    ) -> FliggyQuotePayload:
        raw = client.call(
            self._PRICE_METHOD,
            shid_city_code=shid_city_code,
            start_date=stay_request.checkin_date,
            end_date=stay_request.checkout_date,
            pid=client.pid or None,
        )
        best_room = self._extract_best_room(raw)
        if not best_room:
            raise ServiceIntegrationError(f"飞猪未返回酒店报价：{shid_city_code}")

        price = _safe_float(
            _first_non_empty(
                best_room.get("sale_price"),
                best_room.get("price"),
                best_room.get("member_price"),
                best_room.get("min_price"),
                best_room.get("amount"),
            )
        )
        price_text = _first_non_empty(best_room.get("price_text"), best_room.get("display_price"))
        if price_text in (None, "") and price is not None:
            price_text = f"{price:.0f} 元/晚起"
        room_name = _first_non_empty(best_room.get("name"), best_room.get("room_name"), best_room.get("rpid_name"))
        cancel_desc = _first_non_empty(best_room.get("cancel_desc"), best_room.get("refund_rule"))
        room_summary = "｜".join(str(part) for part in [room_name, cancel_desc] if str(part or "").strip()) or None
        booking_url = client.build_affiliate_url(
            _first_non_empty(
                best_room.get("h5_booking_url"),
                best_room.get("booking_url"),
                best_room.get("buy_url"),
                best_room.get("h5_url"),
                best_room.get("url"),
            )
        )
        return FliggyQuotePayload(
            price=price,
            price_text=str(price_text) if price_text not in (None, "") else None,
            booking_url=booking_url,
            room_summary=room_summary,
            price_source="fliggy_search",
            is_live_price=False,
            raw=dict(best_room),
        )

    def _extract_best_room(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        candidate_rooms: list[dict[str, Any]] = []
        for node in _iter_nested_dicts(payload):
            if not isinstance(node, dict):
                continue
            if any(key in node for key in ("sale_price", "price", "member_price", "display_price", "price_text")):
                candidate_rooms.append(node)
        if not candidate_rooms:
            return None

        def room_key(item: dict[str, Any]) -> tuple[int, float]:
            price = _safe_float(
                _first_non_empty(
                    item.get("sale_price"),
                    item.get("price"),
                    item.get("member_price"),
                    item.get("min_price"),
                    item.get("amount"),
                )
            )
            return (0 if price is not None else 1, price if price is not None else 999999.0)

        candidate_rooms.sort(key=room_key)
        return candidate_rooms[0]

    def _build_candidate(
        self,
        *,
        record: FliggyHotelRecord,
        quote: FliggyQuotePayload | None,
        seed_map: dict[str, dict[str, Any]],
    ) -> HotelCandidate:
        seed = seed_map.get(_normalize_hotel_name(record.name), {})
        distance_m = _safe_int(seed.get("distance_m"))
        price = quote.price if quote else None
        return HotelCandidate(
            id=record.candidate_id,
            name=record.name,
            stay_type=str(seed.get("type") or "酒店"),
            district=record.district or seed.get("business_area"),
            address=record.address or seed.get("address"),
            distance_text=(f"{distance_m} m" if distance_m is not None else None),
            distance_m=distance_m,
            rating=record.rating or _safe_float(seed.get("rating")),
            price=price,
            price_text=quote.price_text if quote else None,
            price_source=quote.price_source if quote else "fliggy_reference",
            is_live_price=quote.is_live_price if quote else False,
            room_summary=quote.room_summary if quote else None,
            provider="fliggy",
            booking_url=quote.booking_url if quote and quote.booking_url else record.h5_detail_url or record.detail_url,
            tel=record.tel or seed.get("tel"),
            location=record.location or seed.get("location"),
            tags=record.tags or ([str(seed.get("business_area"))] if seed.get("business_area") else []),
            raw={
                "record": dict(record.raw),
                "quote": dict(quote.raw) if quote else None,
                "seed": dict(seed) if seed else None,
            },
        )


class FliggyAISkillProvider:
    """飞猪 AI Skill / 搜索 fallback 预留。"""

    provider_name = "fliggy_ai"

    def search_candidates(self, query: HotelSearchQuery) -> HotelSearchResult:
        raise ServiceConfigError("飞猪 AI 酒店搜索未配置，已自动回退。")

    def quote_offer(self, hotel_id: str, stay_request: HotelStayRequest) -> HotelQuoteResult:
        return HotelQuoteResult(
            provider=self.provider_name,
            hotel_id=hotel_id,
            status="unsupported",
            notes=["飞猪 AI 搜索当前仅作候选酒店发现，不提供独立报价。"],
        )


class AmapStayFallbackProvider:
    """高德住宿兜底，只提供地图位置与均价参考。"""

    provider_name = "amap_fallback"

    def __init__(self, amap_service: AmapService | None = None) -> None:
        self.amap_service = amap_service or AmapService()

    def search_candidates(self, query: HotelSearchQuery) -> HotelSearchResult:
        result = self.amap_service.search_stays_with_filters(
            location=query.center,
            radius=query.radius,
            limit=query.limit,
            min_rating=query.min_rating,
            max_budget=query.max_budget,
            max_distance_m=query.max_distance_m,
            include_unknown_budget=True,
            include_unknown_rating=True,
        )
        candidates = [self._normalize_candidate(item) for item in result.get("items") or []]
        return HotelSearchResult(
            provider=self.provider_name,
            provider_mode="fallback",
            status="ok" if candidates else "empty",
            price_status="reference" if candidates else "missing",
            center=query.center,
            destination=query.destination,
            city=query.city,
            radius=query.radius,
            candidates=candidates,
            notes=[
                "当前价格来自高德住宿 POI，仅作均价/最低价参考，不代表实时房态。",
                "如需预订，请前往美团、携程、飞猪等第三方平台核验房态与价格后下单。",
            ],
            fallback_used=True,
            fetched_at=_utc_now_iso(),
        )

    @staticmethod
    def _normalize_candidate(item: dict[str, Any]) -> HotelCandidate:
        resolved_price = _safe_float(item.get("resolved_price"))
        price_source = item.get("price_source")
        price_text = None
        if resolved_price is not None:
            suffix = "起" if price_source == "lowest_price" else ""
            price_text = f"{resolved_price:.0f} 元/晚{suffix}"
        return HotelCandidate(
            id=str(item.get("id") or "") or None,
            name=str(item.get("name") or "未命名住宿"),
            stay_type=str(item.get("type") or "住宿"),
            district=item.get("business_area"),
            address=item.get("address"),
            distance_text=(f"{item.get('distance_m')} m" if item.get("distance_m") is not None else None),
            distance_m=_safe_int(item.get("distance_m")),
            rating=_safe_float(item.get("rating")),
            price=resolved_price,
            price_text=price_text,
            price_source=(
                "amap_lowest_price"
                if price_source == "lowest_price"
                else "amap_cost"
                if price_source == "cost"
                else "unknown"
            ),
            is_live_price=False,
            room_summary=None,
            provider="amap",
            booking_url=None,
            tel=item.get("tel"),
            location=item.get("location"),
            tags=[str(item.get("business_area") or "").strip()] if item.get("business_area") else [],
            raw=dict(item),
        )

    def quote_offer(self, hotel_id: str, stay_request: HotelStayRequest) -> HotelQuoteResult:
        return HotelQuoteResult(
            provider=self.provider_name,
            hotel_id=hotel_id,
            status="reference_only",
            notes=["高德兜底仅提供地图均价或最低价参考，不支持独立实时报价。"],
        )


class HotelService:
    """统一酒店/民宿查询入口。"""

    def __init__(
        self,
        *,
        providers: list[HotelProvider] | None = None,
        amap_service: AmapService | None = None,
    ) -> None:
        self.amap_service = amap_service or AmapService()
        self.providers = providers or [
            AmapStayFallbackProvider(self.amap_service),
        ]

    @staticmethod
    def _ensure_location(amap_service: AmapService, center: str, city: str = "") -> tuple[str, str]:
        raw = (center or "").strip()
        if not raw:
            raise ServiceValidationError("center 不能为空。")
        if "," in raw and len(raw.split(",")) == 2:
            return raw, raw
        geo = amap_service.geocode(address=raw, city=(city or "").strip() or None)
        primary = geo.get("primary") or {}
        location = (primary.get("location") or "").strip()
        if not location:
            raise ServiceValidationError(f"无法解析住宿中心点：{center}")
        return location, primary.get("formatted_address") or raw

    def search_candidates(
        self,
        *,
        destination: str,
        center: str,
        city: str = "",
        radius: int = 5000,
        limit: int = 6,
        max_budget: float | None = None,
        min_rating: float | None = None,
        max_distance_m: int | None = None,
        checkin_date: str = "",
        checkout_date: str = "",
    ) -> HotelSearchResult:
        location, display_center = self._ensure_location(self.amap_service, center, city)
        query = HotelSearchQuery(
            destination=(destination or city or center).strip() or "目的地待补充",
            center=location,
            city=(city or "").strip(),
            radius=radius,
            limit=limit,
            max_budget=max_budget,
            min_rating=min_rating,
            max_distance_m=max_distance_m,
            checkin_date=(checkin_date or "").strip(),
            checkout_date=(checkout_date or "").strip(),
        )

        errors: list[str] = []
        for provider in self.providers:
            try:
                result = provider.search_candidates(query)
            except (ServiceConfigError, ServiceIntegrationError) as exc:
                errors.append(str(exc))
                continue

            if result.candidates:
                result.center = display_center
                if errors:
                    result.notes = list(result.notes) + errors
                return result
            errors.extend(result.notes)

        return HotelSearchResult(
            provider="none",
            provider_mode="unavailable",
            status="empty",
            price_status="missing",
            center=display_center,
            destination=query.destination,
            city=query.city,
            radius=query.radius,
            notes=errors or ["当前没有可用的酒店价格来源，建议稍后重试。"],
            fetched_at=_utc_now_iso(),
        )


_hotel_service: HotelService | None = None


def get_hotel_service() -> HotelService:
    global _hotel_service
    if _hotel_service is None:
        _hotel_service = HotelService()
    return _hotel_service
