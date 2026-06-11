import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """False only for a wrong password; a corrupt/non-argon2 hash raises."""
    try:
        _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    return True


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_session_token() -> tuple[str, str]:
    """Return (cookie_token, db_token_hash)."""
    token = secrets.token_urlsafe(32)
    return token, hash_session_token(token)


def hash_session_token(token: str) -> str:
    # sha256 rather than argon2: the token is 256-bit random (unguessable, no
    # brute-force concern) and lookups must be fast indexed equality checks
    return hashlib.sha256(token.encode()).hexdigest()
