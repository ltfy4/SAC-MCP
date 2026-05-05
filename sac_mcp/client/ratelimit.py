"""Simple async token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """Async token-bucket. ``rate`` is tokens added per second."""

    def __init__(self, rate: float, burst: float | None = None) -> None:
        self.rate = max(rate, 0.0)
        self.capacity = burst if burst is not None else max(rate, 1.0)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, cost: float = 1.0) -> None:
        if self.rate <= 0:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._updated = now
                if self._tokens >= cost:
                    self._tokens -= cost
                    return
                missing = cost - self._tokens
                missing / self.rate
            # unreachable
