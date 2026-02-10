# AI Advisor Bot — Rate Limit Controller (A-P3-06)
# Queuing for API calls to avoid data provider throttling.

import asyncio
import time
from collections import deque
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class RateLimiter:
    """Simple token-bucket style: max N calls per window_sec."""

    def __init__(self, max_calls: int = 10, window_sec: float = 1.0):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self.timestamps: deque[float] = deque()

    async def acquire(self) -> None:
        now = time.monotonic()
        while self.timestamps and self.timestamps[0] < now - self.window_sec:
            self.timestamps.popleft()
        if len(self.timestamps) >= self.max_calls:
            wait = self.timestamps[0] + self.window_sec - now
            if wait > 0:
                await asyncio.sleep(wait)
            return await self.acquire()
        self.timestamps.append(time.monotonic())


_limiter: RateLimiter | None = None


def get_rate_limiter(max_calls: int = 10, window_sec: float = 1.0) -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(max_calls=max_calls, window_sec=window_sec)
    return _limiter


async def with_rate_limit(coro_factory: Callable[[], Any], limiter: RateLimiter | None = None) -> Any:
    """Run coroutine after acquiring rate limit."""
    limiter = limiter or get_rate_limiter()
    await limiter.acquire()
    return await coro_factory()
