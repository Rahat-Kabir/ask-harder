"""In-memory fixed-window rate limiting for the auth endpoints.

Counters live per process and reset on restart — acceptable here because
the app runs as a single instance (the SSE bus already requires that) and
the goal is stopping fast anonymous abuse, not perfect accounting.
"""

import time
from collections.abc import Callable

from fastapi import HTTPException, Request, status


def client_ip(request: Request) -> str:
    """Client identity for rate-limit bucketing.

    Behind the Vercel/Heroku proxies the socket peer is always the router,
    so every visitor would share one bucket. X-Forwarded-For carries the
    real client: each proxy appends the address it saw, so the leftmost
    entry is the origin. Deliberate trade-off: a client that reaches the
    backend directly can forge that entry — accepted because legitimate
    traffic arrives via Vercel (which writes the true client IP), the
    per-email limiter is IP-independent, and the daily interview quota
    bounds cost per account.
    """
    forwarded_chain = request.headers.get("x-forwarded-for")
    if forwarded_chain:
        origin = forwarded_chain.split(",")[0].strip()
        if origin:
            return origin
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._now = now
        # key -> (window_start, count)
        self._hits: dict[str, tuple[float, int]] = {}

    def _prune(self, now: float) -> None:
        # lazy cleanup keeps the dict bounded by recent traffic
        if len(self._hits) > 1024:
            self._hits = {
                key: (start, count)
                for key, (start, count) in self._hits.items()
                if now - start < self.window_seconds
            }

    def hit(self, key: str) -> float | None:
        """Record one attempt. None if allowed; seconds-to-wait if blocked."""
        now = self._now()
        self._prune(now)
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self.window_seconds:
            start, count = now, 0
        count += 1
        self._hits[key] = (start, count)
        if count > self.limit:
            return self.window_seconds - (now - start)
        return None

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def clear(self) -> None:
        self._hits.clear()


# 429 thresholds: generous for humans, hostile to scripts
LOGIN_FAILURES_PER_EMAIL = RateLimiter(limit=5, window_seconds=300)
LOGIN_ATTEMPTS_PER_IP = RateLimiter(limit=20, window_seconds=300)
REGISTRATIONS_PER_IP = RateLimiter(limit=5, window_seconds=3600)


def enforce(limiter: RateLimiter, key: str) -> None:
    retry_after = limiter.hit(key)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts — try again later",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def clear_all() -> None:
    """Test isolation hook — limiters are process-level singletons."""
    LOGIN_FAILURES_PER_EMAIL.clear()
    LOGIN_ATTEMPTS_PER_IP.clear()
    REGISTRATIONS_PER_IP.clear()
