from types import SimpleNamespace

import pytest

from app.auth.rate_limit import RateLimiter, client_ip

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "ratelimit@example.com", "password": "correct-horse-9"}


def fake_request(headers: dict[str, str], peer_host: str | None = "10.0.0.1"):
    """Minimal object with the two attributes client_ip reads. Keys must be
    lowercase here — real Starlette headers are case-insensitive, which the
    endpoint test below covers through the actual ASGI stack."""
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=peer_host) if peer_host else None,
    )


def test_client_ip_uses_leftmost_forwarded_entry():
    request = fake_request({"x-forwarded-for": "203.0.113.7, 76.76.21.9"})
    assert client_ip(request) == "203.0.113.7"


def test_client_ip_trims_whitespace_in_forwarded_entry():
    request = fake_request({"x-forwarded-for": "  203.0.113.7  ,76.76.21.9"})
    assert client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_peer_without_header():
    request = fake_request({})
    assert client_ip(request) == "10.0.0.1"


def test_client_ip_falls_back_to_peer_on_empty_header():
    request = fake_request({"x-forwarded-for": "   "})
    assert client_ip(request) == "10.0.0.1"


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


async def test_forwarded_clients_get_independent_registration_buckets(client):
    # both "clients" share the same socket peer (the test transport), like
    # production traffic sharing the Heroku router — only the forwarded
    # header distinguishes them
    alice = {"X-Forwarded-For": "203.0.113.7, 76.76.21.9"}
    bob = {"X-Forwarded-For": "198.51.100.4, 76.76.21.9"}

    for index in range(5):
        response = await client.post(
            "/api/auth/register",
            json={"email": f"alice{index}@example.com", "password": "delete-me-123"},
            headers=alice,
        )
        assert response.status_code == 201
        await client.post("/api/auth/logout")

    blocked = await client.post(
        "/api/auth/register",
        json={"email": "alice5@example.com", "password": "delete-me-123"},
        headers=alice,
    )
    assert blocked.status_code == 429

    # a different forwarded client is not punished for alice's bucket
    allowed = await client.post(
        "/api/auth/register",
        json={"email": "bob0@example.com", "password": "delete-me-123"},
        headers=bob,
    )
    assert allowed.status_code == 201
