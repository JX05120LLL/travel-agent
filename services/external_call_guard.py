"""外部服务调用治理层。

提供轻量级的：
1. 进程内缓存
2. 限流
3. 熔断
4. 可观测统计
"""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any, Callable

from services.errors import ServiceIntegrationError


@dataclass(slots=True)
class ExternalCallPolicy:
    provider: str
    operation: str
    ttl_seconds: int = 0
    rate_limit: int = 0
    rate_window_seconds: int = 60
    circuit_breaker_threshold: int = 5
    circuit_open_seconds: int = 60


class ExternalCallGuard:
    """统一治理外部调用。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: dict[tuple[str, str, str], tuple[float, Any]] = {}
        self._timestamps: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._state: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "cache_hit_count": 0,
                "degraded_count": 0,
                "consecutive_failures": 0,
                "circuit_open_until": 0.0,
                "last_error": None,
                "last_degraded_reason": None,
            }
        )

    def execute(
        self,
        *,
        policy: ExternalCallPolicy,
        func: Callable[[], Any],
        cache_key: str | None = None,
        fallback: Callable[[Exception], Any] | None = None,
    ) -> Any:
        key = (policy.provider, policy.operation)
        now = monotonic()

        with self._lock:
            state = self._state[key]
            state["call_count"] += 1

            if cache_key and policy.ttl_seconds > 0:
                cached = self._cache.get((policy.provider, policy.operation, cache_key))
                if cached is not None:
                    expires_at, payload = cached
                    if expires_at > now:
                        state["cache_hit_count"] += 1
                        return deepcopy(payload)
                    self._cache.pop((policy.provider, policy.operation, cache_key), None)

            circuit_open_until = float(state["circuit_open_until"] or 0.0)
            if circuit_open_until > now:
                exc = ServiceIntegrationError(
                    f"{policy.provider} 服务当前处于熔断保护中，请稍后重试。"
                )
                state["degraded_count"] += 1
                state["last_degraded_reason"] = "circuit_open"
                if fallback is not None:
                    return fallback(exc)
                raise exc

            if policy.rate_limit > 0:
                timestamps = self._timestamps[key]
                window_start = now - max(policy.rate_window_seconds, 1)
                while timestamps and timestamps[0] < window_start:
                    timestamps.popleft()
                if len(timestamps) >= policy.rate_limit:
                    exc = ServiceIntegrationError(
                        f"{policy.provider} 服务触发限流保护，请稍后重试。"
                    )
                    state["degraded_count"] += 1
                    state["last_degraded_reason"] = "rate_limited"
                    if fallback is not None:
                        return fallback(exc)
                    raise exc
                timestamps.append(now)

        try:
            result = func()
        except Exception as exc:
            with self._lock:
                state = self._state[key]
                state["failure_count"] += 1
                state["consecutive_failures"] += 1
                state["last_error"] = str(exc)
                if state["consecutive_failures"] >= max(policy.circuit_breaker_threshold, 1):
                    state["circuit_open_until"] = now + max(policy.circuit_open_seconds, 1)
            if fallback is not None:
                with self._lock:
                    state = self._state[key]
                    state["degraded_count"] += 1
                    state["last_degraded_reason"] = "fallback_after_error"
                return fallback(exc)
            raise

        with self._lock:
            state = self._state[key]
            state["success_count"] += 1
            state["consecutive_failures"] = 0
            state["circuit_open_until"] = 0.0
            state["last_error"] = None
            if cache_key and policy.ttl_seconds > 0:
                self._cache[(policy.provider, policy.operation, cache_key)] = (
                    now + policy.ttl_seconds,
                    deepcopy(result),
                )
        return result

    def snapshot(self, provider: str | None = None) -> dict[str, Any]:
        with self._lock:
            items: dict[str, Any] = {}
            for (current_provider, operation), state in self._state.items():
                if provider and current_provider != provider:
                    continue
                failure_count = int(state["failure_count"] or 0)
                success_count = int(state["success_count"] or 0)
                total = failure_count + success_count
                items[f"{current_provider}:{operation}"] = {
                    "provider": current_provider,
                    "operation": operation,
                    "call_count": int(state["call_count"] or 0),
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "failure_rate": (failure_count / total) if total else 0.0,
                    "cache_hit_count": int(state["cache_hit_count"] or 0),
                    "degraded_count": int(state["degraded_count"] or 0),
                    "circuit_open": float(state["circuit_open_until"] or 0.0) > monotonic(),
                    "last_error": state["last_error"],
                    "last_degraded_reason": state["last_degraded_reason"],
                }
            return items


external_call_guard = ExternalCallGuard()
