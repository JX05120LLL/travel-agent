import unittest

from services.errors import ServiceIntegrationError
from services.external_call_guard import ExternalCallGuard, ExternalCallPolicy


class ExternalCallGuardTests(unittest.TestCase):
    def test_execute_returns_cached_payload_within_ttl(self):
        guard = ExternalCallGuard()
        policy = ExternalCallPolicy(
            provider="amap",
            operation="geocode",
            ttl_seconds=60,
        )
        call_count = {"value": 0}

        def func():
            call_count["value"] += 1
            return {"result": call_count["value"]}

        first = guard.execute(policy=policy, func=func, cache_key="杭州西湖")
        second = guard.execute(policy=policy, func=func, cache_key="杭州西湖")

        self.assertEqual({"result": 1}, first)
        self.assertEqual({"result": 1}, second)
        self.assertEqual(1, call_count["value"])
        snapshot = guard.snapshot("amap")
        self.assertEqual(1, snapshot["amap:geocode"]["cache_hit_count"])

    def test_execute_applies_rate_limit_with_fallback(self):
        guard = ExternalCallGuard()
        policy = ExternalCallPolicy(
            provider="railway12306",
            operation="arrival_plan",
            rate_limit=1,
            rate_window_seconds=60,
        )

        first = guard.execute(policy=policy, func=lambda: {"ok": True})
        second = guard.execute(
            policy=policy,
            func=lambda: {"ok": True},
            fallback=lambda exc: {"degraded": str(exc)},
        )

        self.assertEqual({"ok": True}, first)
        self.assertIn("限流", second["degraded"])
        snapshot = guard.snapshot("railway12306")
        self.assertEqual("rate_limited", snapshot["railway12306:arrival_plan"]["last_degraded_reason"])

    def test_execute_opens_circuit_after_threshold_failures(self):
        guard = ExternalCallGuard()
        policy = ExternalCallPolicy(
            provider="amap",
            operation="route_transit",
            circuit_breaker_threshold=2,
            circuit_open_seconds=60,
        )

        def failing():
            raise ServiceIntegrationError("上游失败")

        with self.assertRaises(ServiceIntegrationError):
            guard.execute(policy=policy, func=failing)
        with self.assertRaises(ServiceIntegrationError):
            guard.execute(policy=policy, func=failing)
        with self.assertRaises(ServiceIntegrationError):
            guard.execute(policy=policy, func=lambda: {"ok": True})

        snapshot = guard.snapshot("amap")
        self.assertTrue(snapshot["amap:route_transit"]["circuit_open"])
        self.assertEqual(2, snapshot["amap:route_transit"]["failure_count"])


if __name__ == "__main__":
    unittest.main()
