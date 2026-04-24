"""高德 Web API 客户端。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

from services.errors import ServiceConfigError, ServiceIntegrationError
from services.external_call_guard import ExternalCallPolicy, external_call_guard

load_dotenv()


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }


@dataclass(slots=True)
class AmapClient:
    api_key: str
    base_url: str = "https://restapi.amap.com/v3"
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "AmapClient":
        api_key = (
            os.getenv("AMAP_API_KEY", "").strip()
            or os.getenv("AMAP_MAPS_API_KEY", "").strip()
        )
        if not api_key:
            raise ServiceConfigError(
                "未配置高德 API Key，请在 .env 中设置 AMAP_API_KEY。"
            )
        return cls(api_key=api_key)

    def _request(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        request_params = _compact_params(
            {
                "key": self.api_key,
                **params,
            }
        )
        cache_key = json.dumps(
            {
                "path": path,
                "params": _compact_params(params),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        policy = ExternalCallPolicy(
            provider="amap",
            operation=path,
            ttl_seconds=self._cache_ttl_for_path(path),
            rate_limit=180,
            rate_window_seconds=60,
            circuit_breaker_threshold=5,
            circuit_open_seconds=60,
        )
        return external_call_guard.execute(
            policy=policy,
            cache_key=cache_key,
            func=lambda: self._do_request(path, request_params=request_params),
        )

    def _do_request(self, path: str, *, request_params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                params=request_params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ServiceIntegrationError("请求高德接口超时，请稍后重试。") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise ServiceIntegrationError(
                f"高德接口 HTTP 错误：{exc.response.status_code}，{detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceIntegrationError(f"高德接口请求失败：{exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceIntegrationError("高德接口返回了非 JSON 响应。") from exc

        status = str(payload.get("status", ""))
        if status != "1":
            info = payload.get("info") or "未知错误"
            infocode = payload.get("infocode")
            detail = payload.get("info_detail")
            error_message = f"高德接口返回失败：{info}"
            if infocode:
                error_message += f"（infocode={infocode}）"
            if detail:
                error_message += f"（{detail}）"
            raise ServiceIntegrationError(error_message)

        return payload

    @staticmethod
    def _cache_ttl_for_path(path: str) -> int:
        ttl_mapping = {
            "/geocode/geo": 6 * 60 * 60,
            "/geocode/regeo": 60 * 60,
            "/place/text": 15 * 60,
            "/place/around": 10 * 60,
            "/direction/driving": 15 * 60,
            "/direction/walking": 15 * 60,
            "/direction/transit/integrated": 15 * 60,
            "/weather/weatherInfo": 30 * 60,
        }
        return ttl_mapping.get(path, 5 * 60)

    def geocode(self, *, address: str, city: str | None = None) -> dict[str, Any]:
        return self._request(
            "/geocode/geo",
            params={
                "address": address,
                "city": city,
            },
        )

    def reverse_geocode(
        self,
        *,
        location: str,
        radius: int = 1000,
        extensions: str = "base",
        roadlevel: int = 0,
    ) -> dict[str, Any]:
        return self._request(
            "/geocode/regeo",
            params={
                "location": location,
                "radius": radius,
                "extensions": extensions,
                "roadlevel": roadlevel,
            },
        )

    def search_poi(
        self,
        *,
        keywords: str,
        city: str | None = None,
        city_limit: bool = True,
        types: str | None = None,
        page: int = 1,
        offset: int = 10,
    ) -> dict[str, Any]:
        return self._request(
            "/place/text",
            params={
                "keywords": keywords,
                "city": city,
                "citylimit": "true" if city_limit else "false",
                "types": types,
                "page": page,
                "offset": offset,
                "extensions": "all",
            },
        )

    def search_around(
        self,
        *,
        location: str,
        keywords: str | None = None,
        types: str | None = None,
        radius: int = 3000,
        sortrule: str = "distance",
        page: int = 1,
        offset: int = 10,
    ) -> dict[str, Any]:
        return self._request(
            "/place/around",
            params={
                "location": location,
                "keywords": keywords,
                "types": types,
                "radius": radius,
                "sortrule": sortrule,
                "page": page,
                "offset": offset,
                "extensions": "all",
            },
        )

    def route_driving(
        self,
        *,
        origin: str,
        destination: str,
        strategy: int = 0,
        extensions: str = "base",
    ) -> dict[str, Any]:
        return self._request(
            "/direction/driving",
            params={
                "origin": origin,
                "destination": destination,
                "strategy": strategy,
                "extensions": extensions,
            },
        )

    def route_walking(
        self,
        *,
        origin: str,
        destination: str,
    ) -> dict[str, Any]:
        return self._request(
            "/direction/walking",
            params={
                "origin": origin,
                "destination": destination,
            },
        )

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
        return self._request(
            "/direction/transit/integrated",
            params={
                "origin": origin,
                "destination": destination,
                "city": city,
                "cityd": cityd,
                "strategy": strategy,
                "nightflag": nightflag,
                "extensions": extensions,
            },
        )

    def weather(self, *, city: str, extensions: str = "base") -> dict[str, Any]:
        return self._request(
            "/weather/weatherInfo",
            params={
                "city": city,
                "extensions": extensions,
            },
        )
