from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, DbSession
from app.auth.rate_limit import (
    LOGIN_ATTEMPTS_PER_IP,
    LOGIN_FAILURES_PER_EMAIL,
    REGISTRATIONS_PER_IP,
    client_ip,
    enforce,
)
from app.auth.schemas import LoginIn, RegisterIn, UserOut
from app.auth.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from app.config import settings
from app.db.models import User, UserSession

router = APIRouter(tags=["auth"])


async def _start_session(db: AsyncSession, user: User, response: Response) -> None:
    cookie_token, token_hash = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.session_ttl_days)
    db.add(UserSession(token_hash=token_hash, user_id=user.id, expires_at=expires_at))
    response.set_cookie(
        settings.session_cookie_name,
        cookie_token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        # secure cookies don't survive plain-http localhost in dev
        secure=settings.app_env != "dev",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name)


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request, body: RegisterIn, db: DbSession, response: Response
) -> UserOut:
    # throttles junk-account farming — also what keeps the per-account
    # interview quota meaningful
    enforce(REGISTRATIONS_PER_IP, client_ip(request))
    user = User(
        email=body.email.strip().lower(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email already registered"
        ) from None
    # registering logs you in — no second roundtrip
    await _start_session(db, user, response)
    await db.commit()
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/auth/login")
async def login(
    request: Request, body: LoginIn, db: DbSession, response: Response
) -> UserOut:
    enforce(LOGIN_ATTEMPTS_PER_IP, client_ip(request))
    email = body.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    # same 401 whether the email or the password was wrong — don't reveal
    # which emails are registered
    if user is None or not verify_password(user.password_hash, body.password):
        # failures only — a human re-typing a remembered password never
        # trips this; a password-guesser always does
        enforce(LOGIN_FAILURES_PER_EMAIL, email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    LOGIN_FAILURES_PER_EMAIL.reset(email)

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    await _start_session(db, user, response)
    await db.commit()
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    db: DbSession,
    response: Response,
    session_token: Annotated[
        str | None, Cookie(alias=settings.session_cookie_name)
    ] = None,
) -> None:
    # idempotent: logging out without a session is still a 204
    if session_token is not None:
        await db.execute(
            delete(UserSession).where(
                UserSession.token_hash == hash_session_token(session_token)
            )
        )
        await db.commit()
    _clear_session_cookie(response)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, db: DbSession, response: Response) -> None:
    # sessions go with the user via FK ON DELETE CASCADE; future tables
    # (interviews, evaluations, ...) must follow the same pattern
    await db.delete(user)
    await db.commit()
    _clear_session_cookie(response)
