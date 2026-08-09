"""Pacing primitives: thread-safe token-bucket rate limiting.

A ``RateLimiter`` allows ``rate`` requests per second, with a burst capacity
of 1 by default (matching the old ``rate_delay`` semantics: first request is
free, then ``1/rate`` seconds between each).  ``rate=0`` disables throttling.

``Pacing`` is a per-provider registry that returns cached ``RateLimiter``
instances so multiple phases (search + download) share one bucket.

Example::

    from soundfetch.core.pacing import Pacing

    pacing = Pacing()
    pacing.set_rate("freesound", 0.9)  # ~54 req/min, under Freesound's 60 cap
    limiter = pacing.limiter("freesound")
"""

from __future__ import annotations

import threading
import time
from typing import Callable

# Sensible defaults (requests/sec); overridden by CLI flags or caller.
DEFAULT_RATES: dict[str, float] = {
    "freesound": 0.9,   # ~54/min — safely under the 60/min cap
    "archive": 4.0,
    "video": 0.5,
}


class RateLimiter:
    """Thread-safe token-bucket rate limiter.

    Allows ``rate`` requests per second with burst capacity 1 (first request
    is free, then 1/rate seconds spacing).  ``rate=0`` disables throttling.

    ``sleep`` defaults to ``time.sleep`` (resolved dynamically at construction
    so monkeypatching ``time.sleep`` before constructing a ``RateLimiter``
    works as expected).
    """

    def __init__(
        self,
        rate: float,
        capacity: float = 1.0,
        *,
        sleep: Callable[[float], None] | None = None,
    ):
        self._rate = max(0.0, float(rate))
        self._capacity = max(0.0, float(capacity))
        # Resolve sleep at construction so monkeypatched time.sleep is picked up.
        self._sleep: Callable[[float], None] = sleep if sleep is not None else time.sleep
        self._lock = threading.Lock()
        self._tokens = self._capacity
        self._last = time.monotonic()

    @property
    def rate(self) -> float:
        return self._rate

    def set_rate(self, rate: float) -> None:
        """Update the request rate (for dynamic pacing adjustments)."""
        with self._lock:
            self._rate = max(0.0, float(rate))

    def acquire(self) -> None:
        """Block until a token is available, then consume it.

        When ``rate == 0``, returns immediately (no throttling).

        Implementation sleeps at most once per call, avoiding a busy-loop
        when the injected ``sleep`` does not advance ``time.monotonic()``
        (e.g. a no-op monkeypatch in tests).
        """
        if self._rate <= 0:
            return
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._last) * self._rate,
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self._rate
            # Commit the wait so concurrent threads see accurate state;
            # set _last forward so refill after wake doesn't double-count.
            self._tokens = 0.0
            self._last = now + wait
        self._sleep(wait)


class Pacing:
    """Per-provider rate-limiter registry.

    ``limiter(name)`` returns a cached ``RateLimiter`` for that provider.
    Call ``set_rate`` before the first ``limiter()`` call to set a custom rate.
    """

    def __init__(
        self,
        rates: dict[str, float] | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
    ):
        self._rates = dict(DEFAULT_RATES)
        if rates:
            self._rates.update(rates)
        self._sleep = sleep
        self._limiters: dict[str, RateLimiter] = {}
        self._lock = threading.Lock()

    def set_rate(self, name: str, rate: float) -> None:
        """Set the rate for a provider, updating any existing limiter."""
        with self._lock:
            self._rates[name] = rate
            if name in self._limiters:
                self._limiters[name].set_rate(rate)

    def limiter(self, name: str) -> RateLimiter:
        """Return a cached ``RateLimiter`` for *name*."""
        with self._lock:
            if name not in self._limiters:
                rate = self._rates.get(name, 0.0)
                self._limiters[name] = RateLimiter(rate, sleep=self._sleep)
            return self._limiters[name]

    def acquire(self, name: str) -> None:
        """Convenience: acquire a token for *name*."""
        self.limiter(name).acquire()


_default_pacing: Pacing | None = None
_default_lock = threading.Lock()


def default_pacing() -> Pacing:
    """Process-global default ``Pacing`` instance (for library callers)."""
    global _default_pacing
    if _default_pacing is None:
        with _default_lock:
            if _default_pacing is None:
                _default_pacing = Pacing()
    return _default_pacing
