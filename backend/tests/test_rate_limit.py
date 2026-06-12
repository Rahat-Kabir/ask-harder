import pytest

from app.auth.rate_limit import RateLimiter

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "ratelimit@example.com", "password": "correct-horse-9"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_limit_then_blocks():
    clock = FakeClock()
    limiter = RateLimiter(limit=3, window_seconds=60, now=clock)

    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    retry_after = limiter.hit("k")
    assert retry_after is not None
    assert 0 < retry_after <= 60


def test_limiter_window_expires_and_resets():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, now=clock)

    assert limiter.hit("k") is None
    assert limiter.hit("k") is not None
    clock.now += 61
    assert limiter.hit("k") is None


def test_limiter_keys_are_independent():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, now=clock)

    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None
    assert limiter.hit("b") is None


def test_limiter_reset_clears_one_key():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, now=clock)

    limiter.hit("k")
    assert limiter.hit("k") is not None
    limiter.reset("k")
    assert limiter.hit("k") is None


async def test_sixth_failed_login_is_429_with_retry_after(client):
    register = await client.post("/api/auth/register", json=CREDENTIALS)
    assert register.status_code == 201
    await client.post("/api/auth/logout")

    bad = {"email": CREDENTIALS["email"], "password": "wrong-password-1"}
    for _ in range(5):
        response = await client.post("/api/auth/login", json=bad)
        assert response.status_code == 401

    blocked = await client.post("/api/auth/login", json=bad)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_successful_login_resets_failure_count(client):
    register = await client.post("/api/auth/register", json=CREDENTIALS)
    assert register.status_code == 201
    await client.post("/api/auth/logout")

    bad = {"email": CREDENTIALS["email"], "password": "wrong-password-1"}
    for _ in range(4):
        await client.post("/api/auth/login", json=bad)

    ok = await client.post("/api/auth/login", json=CREDENTIALS)
    assert ok.status_code == 200
    await client.post("/api/auth/logout")

    # the failure counter restarted — old failures don't linger
    for _ in range(5):
        response = await client.post("/api/auth/login", json=bad)
        assert response.status_code == 401


async def test_sixth_registration_from_one_ip_is_429(client):
    for index in range(5):
        response = await client.post(
            "/api/auth/register",
            json={"email": f"bulk{index}@example.com", "password": "delete-me-123"},
        )
        assert response.status_code == 201
        await client.post("/api/auth/logout")

    blocked = await client.post(
        "/api/auth/register",
        json={"email": "bulk5@example.com", "password": "delete-me-123"},
    )
    assert blocked.status_code == 429
