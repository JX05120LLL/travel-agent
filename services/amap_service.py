"""高德业务服务层。

这一层负责把第三方返回转成项目内更稳定的数据结构，
避免 Web 层直接依赖高德原始字段。
"""

from __future__ import annotations

import re
from typing import Any

from services.errors import ServiceValidationError
from services.integrations.amap_client import AmapClient

_LOCATION_PATTERN = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")
AMAP_TYPECODE_FOOD = "050000"
AMAP_TYPECODE_STAY = "100000"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    """把高德返回的字符串/数字/空数组转成 float。"""
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class AmapService:
    """高德能力聚合服务。"""

    def __init__(self, client: AmapClient | None = None):
        self.client = client or AmapClient.from_env()

    @staticmethod
    def _ensure_text(value: str, *, field_name: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ServiceValidationError(f"{field_name} 不能为空。")
        return text

    @staticmethod
    def _ensure_location(value: str, *, field_name: str = "location") -> str:
        location = (value or "").strip()
        if not location:
            raise ServiceValidationError(f"{field_name} 不能为空，应为 lng,lat。")
        if not _LOCATION_PATTERN.match(location):
            raise ServiceValidationError(
                f"{field_name} 格式不正确，应为 lng,lat，例如 116.481488,39.990464。"
            )
        return location

    @staticmethod
    def _serialize_poi_item(item: dict[str, Any]) -> dict[str, Any]:
        """统一 POI 输出结构，便于前端和工具层复用。"""
        biz_ext = item.get("biz_ext") or {}
        rating = _to_float(biz_ext.get("rating"))
        cost = _to_float(biz_ext.get("cost"))
        lowest_price = _to_float(biz_ext.get("lowest_price"))
        distance = _to_int(item.get("distance"), default=-1)
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "typecode": item.get("typecode"),
            "address": item.get("address"),
            "location": item.get("location"),
            "distance": item.get("distance"),
            "distance_m": (distance if distance >= 0 else None),
            "tel": item.get("tel"),
            "business_area": item.get("business_area"),
            "rating": rating,
            "cost": cost,
            "lowest_price": lowest_price,
            "biz_ext": biz_ext if isinstance(biz_ext, dict) else {},
        }

    def geocode(self, *, address: str, city: str | None = None) -> dict[str, Any]:
        """地址转经纬度。"""
        address = self._ensure_text(address, field_name="address")
        payload = self.client.geocode(address=address, city=(city or "").strip() or None)
        geocodes = payload.get("geocodes") or []
        items = [
            {
                "formatted_address": item.get("formatted_address"),
                "province": item.get("province"),
                "city": item.get("city"),
                "district": item.get("district"),
                "adcode": item.get("adcode"),
                "location": item.get("location"),
                "level": item.get("level"),
            }
            for item in geocodes
        ]
        return {
            "query": {
                "address": address,
                "city": (city or "").strip() or None,
            },
            "count": _to_int(payload.get("count")),
            "primary": items[0] if items else None,
            "items": items,
            "raw": payload,
        }

    def reverse_geocode(
        self,
        *,
        location: str,
        radius: int = 1000,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """经纬度转地址。"""
        location = self._ensure_location(location)
        if radius <= 0:
            raise ServiceValidationError("radius 必须大于 0。")
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.reverse_geocode(
            location=location,
            radius=radius,
            extensions=extensions,
        )
        regeo = payload.get("regeocode") or {}
        address_component = regeo.get("addressComponent") or {}
        return {
            "query": {
                "location": location,
                "radius": radius,
                "extensions": extensions,
            },
            "formatted_address": regeo.get("formatted_address"),
            "province": address_component.get("province"),
            "city": address_component.get("city"),
            "district": address_component.get("district"),
            "township": address_component.get("township"),
            "adcode": address_component.get("adcode"),
            "pois": regeo.get("pois") or [],
            "roads": regeo.get("roads") or [],
            "raw": payload,
        }

    def search_poi(
        self,
        *,
        keywords: str,
        city: str | None = None,
        city_limit: bool = True,
        types: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """POI 搜索。"""
        keywords = self._ensure_text(keywords, field_name="keywords")
        if page <= 0:
            raise ServiceValidationError("page 必须大于 0。")
        if page_size <= 0 or page_size > 25:
            raise ServiceValidationError("page_size 必须在 1-25 之间。")

        payload = self.client.search_poi(
            keywords=keywords,
            city=(city or "").strip() or None,
            city_limit=city_limit,
            types=(types or "").strip() or None,
            page=page,
            offset=page_size,
        )
        pois = payload.get("pois") or []
        items = [self._serialize_poi_item(item) for item in pois]
        return {
            "query": {
                "keywords": keywords,
                "city": (city or "").strip() or None,
                "city_limit": city_limit,
                "types": (types or "").strip() or None,
                "page": page,
                "page_size": page_size,
            },
            "count": _to_int(payload.get("count")),
            "items": items,
            "raw": payload,
        }

    def search_nearby(
        self,
        *,
        location: str,
        keywords: str | None = None,
        types: str | None = None,
        radius: int = 3000,
        page: int = 1,
        page_size: int = 10,
        sortrule: str = "distance",
    ) -> dict[str, Any]:
        """周边检索。"""
        location = self._ensure_location(location)
        if radius <= 0 or radius > 50000:
            raise ServiceValidationError("radius 必须在 1-50000 米之间。")
        if page <= 0:
            raise ServiceValidationError("page 必须大于 0。")
        if page_size <= 0 or page_size > 25:
            raise ServiceValidationError("page_size 必须在 1-25 之间。")
        if sortrule not in {"distance", "weight"}:
            raise ServiceValidationError("sortrule 仅支持 distance 或 weight。")

        payload = self.client.search_around(
            location=location,
            keywords=(keywords or "").strip() or None,
            types=(types or "").strip() or None,
            radius=radius,
            sortrule=sortrule,
            page=page,
            offset=page_size,
        )
        pois = payload.get("pois") or []
        items = [self._serialize_poi_item(item) for item in pois]
        return {
            "query": {
                "location": location,
                "keywords": (keywords or "").strip() or None,
                "types": (types or "").strip() or None,
                "radius": radius,
                "page": page,
                "page_size": page_size,
                "sortrule": sortrule,
            },
            "count": _to_int(payload.get("count")),
            "items": items,
            "raw": payload,
        }

    def search_nearby_food(
        self,
        *,
        location: str,
        radius: int = 3000,
        page: int = 1,
        page_size: int = 10,
        sortrule: str = "distance",
    ) -> dict[str, Any]:
        """周边美食检索。"""
        return self.search_nearby(
            location=location,
            types=AMAP_TYPECODE_FOOD,
            radius=radius,
            page=page,
            page_size=page_size,
            sortrule=sortrule,
        )

    def search_nearby_stay(
        self,
        *,
        location: str,
        keyword: str | None = None,
        radius: int = 5000,
        page: int = 1,
        page_size: int = 10,
        sortrule: str = "distance",
    ) -> dict[str, Any]:
        """周边住宿检索（酒店/民宿）。"""
        return self.search_nearby(
            location=location,
            keywords=keyword,
            types=AMAP_TYPECODE_STAY,
            radius=radius,
            page=page,
            page_size=page_size,
            sortrule=sortrule,
        )

    def search_stays_with_filters(
        self,
        *,
        location: str,
        radius: int = 5000,
        limit: int = 10,
        min_rating: float | None = None,
        max_budget: float | None = None,
        max_distance_m: int | None = None,
        include_unknown_rating: bool = True,
        include_unknown_budget: bool = True,
    ) -> dict[str, Any]:
        """酒店/民宿检索 + 筛选（预算、评分、距离）。"""
        location = self._ensure_location(location)
        if radius <= 0 or radius > 50000:
            raise ServiceValidationError("radius 必须在 1-50000 米之间。")
        if limit <= 0 or limit > 25:
            raise ServiceValidationError("limit 必须在 1-25 之间。")
        if min_rating is not None and not (0 <= min_rating <= 5):
            raise ServiceValidationError("min_rating 必须在 0-5 之间。")
        if max_budget is not None and max_budget <= 0:
            raise ServiceValidationError("max_budget 必须大于 0。")
        if max_distance_m is not None and max_distance_m <= 0:
            raise ServiceValidationError("max_distance_m 必须大于 0。")

        hotel_result = self.search_nearby_stay(
            location=location,
            keyword="酒店",
            radius=radius,
            page=1,
            page_size=limit,
        )
        homestay_result = self.search_nearby_stay(
            location=location,
            keyword="民宿",
            radius=radius,
            page=1,
            page_size=limit,
        )
        merged = self._merge_unique_poi_items(
            hotel_result.get("items") or [],
            homestay_result.get("items") or [],
        )
        before_filter_count = len(merged)
        filtered = [
            item
            for item in merged
            if self._match_stay_filters(
                item=item,
                min_rating=min_rating,
                max_budget=max_budget,
                max_distance_m=max_distance_m,
                include_unknown_rating=include_unknown_rating,
                include_unknown_budget=include_unknown_budget,
            )
        ]
        filtered.sort(
            key=lambda x: (
                x.get("distance_m") if x.get("distance_m") is not None else 10**9,
                -(x.get("rating") if x.get("rating") is not None else -1),
                x.get("cost") if x.get("cost") is not None else 10**9,
            )
        )
        return {
            "query": {
                "location": location,
                "radius": radius,
                "limit": limit,
                "min_rating": min_rating,
                "max_budget": max_budget,
                "max_distance_m": max_distance_m,
                "include_unknown_rating": include_unknown_rating,
                "include_unknown_budget": include_unknown_budget,
            },
            "before_filter_count": before_filter_count,
            "count": len(filtered),
            "items": filtered[:limit],
        }

    @staticmethod
    def _merge_unique_poi_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按 id+location 去重合并。"""
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            for item in group:
                key = (
                    str(item.get("id") or item.get("name") or ""),
                    str(item.get("location") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    @staticmethod
    def _match_stay_filters(
        *,
        item: dict[str, Any],
        min_rating: float | None,
        max_budget: float | None,
        max_distance_m: int | None,
        include_unknown_rating: bool,
        include_unknown_budget: bool,
    ) -> bool:
        """判断住宿是否命中筛选条件。"""
        distance_m = item.get("distance_m")
        rating = item.get("rating")
        budget = item.get("cost")

        if max_distance_m is not None:
            if distance_m is None:
                return False
            if distance_m > max_distance_m:
                return False

        if min_rating is not None:
            if rating is None and not include_unknown_rating:
                return False
            if rating is not None and rating < min_rating:
                return False

        if max_budget is not None:
            if budget is None and not include_unknown_budget:
                return False
            if budget is not None and budget > max_budget:
                return False

        return True

    def route_driving(
        self,
        *,
        origin: str,
        destination: str,
        strategy: int = 0,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """驾车路线。"""
        origin = self._ensure_location(origin, field_name="origin")
        destination = self._ensure_location(destination, field_name="destination")
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.route_driving(
            origin=origin,
            destination=destination,
            strategy=strategy,
            extensions=extensions,
        )
        route = payload.get("route") or {}
        paths = route.get("paths") or []
        return {
            "query": {
                "origin": origin,
                "destination": destination,
                "strategy": strategy,
                "extensions": extensions,
            },
            "origin": route.get("origin"),
            "destination": route.get("destination"),
            "taxi_cost": route.get("taxi_cost"),
            "path_count": len(paths),
            "paths": paths,
            "primary_path": paths[0] if paths else None,
            "raw": payload,
        }

    def route_walking(self, *, origin: str, destination: str) -> dict[str, Any]:
        """步行路线。"""
        origin = self._ensure_location(origin, field_name="origin")
        destination = self._ensure_location(destination, field_name="destination")

        payload = self.client.route_walking(origin=origin, destination=destination)
        route = payload.get("route") or {}
        paths = route.get("paths") or []
        return {
            "query": {
                "origin": origin,
                "destination": destination,
            },
            "path_count": len(paths),
            "paths": paths,
            "primary_path": paths[0] if paths else None,
            "raw": payload,
        }

    def route_transit(
        self,
        *,
        origin: str,
        destination: str,
        city: str,
        cityd: str | None = None,
        strategy: int = 0,
        nightflag: int = 0,
        extensions: str = "base",
    ) -> dict[str, Any]:
        """公交/地铁路线。"""
        origin = self._ensure_location(origin, field_name="origin")
        destination = self._ensure_location(destination, field_name="destination")
        city = self._ensure_text(city, field_name="city")
        cityd = (cityd or "").strip() or None
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.route_transit(
            origin=origin,
            destination=destination,
            city=city,
            cityd=cityd,
            strategy=strategy,
            nightflag=nightflag,
            extensions=extensions,
        )
        route = payload.get("route") or {}
        transits = route.get("transits") or []
        return {
            "query": {
                "origin": origin,
                "destination": destination,
                "city": city,
                "cityd": cityd,
                "strategy": strategy,
                "nightflag": nightflag,
                "extensions": extensions,
            },
            "path_count": len(transits),
            "transits": transits,
            "primary_transit": transits[0] if transits else None,
            "raw": payload,
        }

    def weather(self, *, city: str, extensions: str = "base") -> dict[str, Any]:
        """城市天气。"""
        city = self._ensure_text(city, field_name="city")
        if extensions not in {"base", "all"}:
            raise ServiceValidationError("extensions 仅支持 base 或 all。")

        payload = self.client.weather(city=city, extensions=extensions)
        return {
            "query": {
                "city": city,
                "extensions": extensions,
            },
            "lives": payload.get("lives") or [],
            "forecasts": payload.get("forecasts") or [],
            "raw": payload,
        }
