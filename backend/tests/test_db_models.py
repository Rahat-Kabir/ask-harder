"""Schema-shape tests — no database needed, they inspect Base.metadata."""

from app.db import models  # noqa: F401  — registers models on Base.metadata
from app.db.base import Base


def test_users_table_registered() -> None:
    assert "users" in Base.metadata.tables


def test_users_email_is_unique() -> None:
    table = Base.metadata.tables["users"]
    unique_constraints = [c.name for c in table.constraints if c.name]
    assert "uq_users_email" in unique_constraints
