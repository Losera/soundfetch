"""Unit tests for soundfetch.core.pacing — token-bucket rate limiter + registry."""

from __future__ import annotations

import threading

import pytest

from soundfetch.core.pacing import Pacing, RateLimiter


# ---------------------------------------------------------------------------
# RateLimiter basics
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_first_acquire_is_free(self):
        """First acquire returns immediately (burst capacity = 1)."""
        sleeps: list[float] = []
        limiter = RateLimiter(2.0, sleep=sleeps.append)  # 2 req/s → 0.5s
        limiter.acquire()
        assert sleeps == []

    def test_subsequent_acquire_sleeps(self):
        """Second acquire sleeps ~1/rate seconds."""
        sleeps: list[float] = []
        limiter = RateLimiter(2.0, sleep=sleeps.append)
        limiter.acquire()  # free
        limiter.acquire()
        assert len(sleeps) == 1
        assert sleeps[0] == pytest.approx(0.5, abs=0.01)

    def test_rate_zero_disables_throttling(self):
        """rate=0 → no sleep at all, ever."""
        sleeps: list[float] = []
        limiter = RateLimiter(0.0, sleep=sleeps.append)
        for _ in range(100):
            limiter.acquire()
        assert sleeps == []

    def test_set_rate_updates_existing_limiter(self):
        """set_rate dynamically changes the throttle without creating a new instance."""
        sleeps: list[float] = []
        limiter = RateLimiter(2.0, sleep=sleeps.append)
        limiter.acquire()  # free
        limiter.set_rate(10.0)  # 10 req/s → 0.1s
        limiter.acquire()
        assert sleeps[0] == pytest.approx(0.1, abs=0.01)

    def test_sleeps_exactly_once_per_acquire(self):
        """Each acquire sleeps at most once (no busy-loop even with a no-op sleep)."""
        call_count = 0

        def noop_sleep(_: float) -> None:
            nonlocal call_count
            call_count += 1

        limiter = RateLimiter(2.0, sleep=noop_sleep)
        limiter.acquire()  # free
        limiter.acquire()  # should sleep exactly once
        assert call_count == 1

    def test_acquire_no_busy_loop(self):
        """Under a no-op sleep, acquire() terminates (no infinite spin)."""
        limiter = RateLimiter(2.0, sleep=lambda _: None)
        limiter.acquire()  # free
        limiter.acquire()  # must terminate
        limiter.acquire()  # must also terminate
        # If we get here, no busy-loop


# ---------------------------------------------------------------------------
# Pacing registry
# ---------------------------------------------------------------------------


class TestPacing:
    def test_limiter_is_cached(self):
        """Calling limiter() twice with the same name returns the same instance."""
        pacing = Pacing()
        a = pacing.limiter("freesound")
        b = pacing.limiter("freesound")
        assert a is b

    def test_different_providers_get_different_limiters(self):
        pacing = Pacing()
        a = pacing.limiter("freesound")
        b = pacing.limiter("archive")
        assert a is not b

    def test_custom_rate(self):
        """rates dict overrides the default."""
        pacing = Pacing(rates={"custom": 10.0})
        limiter = pacing.limiter("custom")
        assert limiter.rate == pytest.approx(10.0)

    def test_default_rates(self):
        pacing = Pacing()
        assert pacing.limiter("freesound").rate == pytest.approx(0.9)
        assert pacing.limiter("archive").rate == pytest.approx(4.0)

    def test_set_rate_updates_existing_limiter(self):
        pacing = Pacing()
        limiter = pacing.limiter("freesound")
        pacing.set_rate("freesound", 5.0)
        assert limiter.rate == pytest.approx(5.0)

    def test_set_rate_injects_custom_sleep(self):
        """Sleep callable from Pacing is passed through to each RateLimiter."""
        sleeps: list[float] = []
        pacing = Pacing(rates={"test": 10.0}, sleep=sleeps.append)
        limiter = pacing.limiter("test")
        limiter.acquire()  # free
        limiter.acquire()
        assert len(sleeps) == 1
        assert sleeps[0] == pytest.approx(0.1, abs=0.01)
