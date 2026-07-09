"""A thread-safe token-bucket rate limiter.

The concurrent crossover runs many answering/embedding calls in flight; a
hosted API caps requests per minute. `RateLimiter.acquire()` blocks the caller
until a token is available, so the pool self-throttles to the configured rate
without any arm ever exceeding it. Deterministic in effect (it only delays, it
never changes what a call returns), so results stay byte-identical to a
sequential run.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """At most `rpm` acquisitions per minute, refilling continuously.

    A classic token bucket: tokens accrue at `rpm / 60` per second up to a
    burst `capacity` (default: one minute's worth, so a fresh limiter can fire
    a burst then settle to the steady rate). `acquire()` is thread-safe and
    blocks (sleeping outside the lock) until a whole token is available.
    """

    def __init__(self, rpm: float, capacity: float | None = None) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be positive")
        self.rate = rpm / 60.0
        self.capacity = float(capacity) if capacity is not None else max(1.0, rpm)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._last) * self.rate
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self.rate
            time.sleep(wait)
