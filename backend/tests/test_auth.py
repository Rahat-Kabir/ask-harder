import pytest
from sqlalchemy import select

from app.db.models import User, UserSession
from app.db.session import new_session

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "dev@example.com", "password": "correct-horse-9"}


async def test_register_logs_in_and_me_works(client):
    response = await client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 201
    assert response.json()["email"] == CREDENTIALS["email"]
    assert "askharder_session" in response.cookies

    me = await client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == CREDENTIALS["email"]


async def test_password_is_stored_as_argon2_hash(client):
    await client.post("/api/auth/register", json=CREDENTIALS)
    async with new_session() as db:
        user = (await db.execute(select(User))).scalar_one()
    assert user.password_hash.startswith("$argon2")
    assert CREDENTIALS["password"] not in user.password_hash


async def test_duplicate_email_is_409(client):
    await client.post("/api/auth/register", json=CREDENTIALS)
    response = await client.post(
        "/api/auth/register",
        json={"email": CREDENTIALS["email"].upper(), "password": "another-pass-1"},
    )
    assert response.status_code == 409


async def test_short_password_is_422(client):
    response = await client.post(
        "/api/auth/register", json={"email": "a@b.com", "password": "short"}
    )
    assert response.status_code == 422


async def test_login_with_wrong_password_is_401(client):
    await client.post("/api/auth/register", json=CREDENTIALS)
    response = await client.post(
        "/api/auth/login",
        json={"email": CREDENTIALS["email"], "password": "wrong-password-1"},
    )
    assert response.status_code == 401


async def test_login_unknown_email_is_401(client):
    response = await client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "whatever-123"},
    )
    assert response.status_code == 401


async def test_login_works_after_logout(client):
    await client.post("/api/auth/register", json=CREDENTIALS)

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert (await client.get("/api/me")).status_code == 401

    login = await client.post("/api/auth/login", json=CREDENTIALS)
    assert login.status_code == 200
    assert (await client.get("/api/me")).status_code == 200


async def test_save_resume_roundtrips_through_me(client):
    await client.post("/api/auth/register", json=CREDENTIALS)

    saved = await client.put(
        "/api/me/resume",
        json={"resume_text": "Built a billing reconciliation service."},
    )
    assert saved.status_code == 200
    assert saved.json()["resume_text"] == "Built a billing reconciliation service."

    me = await client.get("/api/me")
    assert me.json()["resume_text"] == "Built a billing reconciliation service."


async def test_blank_resume_clears_saved_value(client):
    await client.post("/api/auth/register", json=CREDENTIALS)
    await client.put("/api/me/resume", json={"resume_text": "Something."})

    cleared = await client.put("/api/me/resume", json={"resume_text": "   "})
    assert cleared.status_code == 200
    assert cleared.json()["resume_text"] is None


async def test_save_resume_requires_auth(client):
    response = await client.put("/api/me/resume", json={"resume_text": "x"})
    assert response.status_code == 401


async def test_me_without_cookie_is_401(client):
    assert (await client.get("/api/me")).status_code == 401


async def test_delete_me_cascades_sessions(client):
    await client.post("/api/auth/register", json=CREDENTIALS)

    response = await client.delete("/api/me")
    assert response.status_code == 204
    assert (await client.get("/api/me")).status_code == 401

    # user gone, sessions cascaded - verified in the DB, not just via the API
    async with new_session() as db:
        assert (await db.execute(select(User))).first() is None
        assert (await db.execute(select(UserSession))).first() is None

    login = await client.post("/api/auth/login", json=CREDENTIALS)
    assert login.status_code == 401
