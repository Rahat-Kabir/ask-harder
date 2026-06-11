"""turns.sequence — explicit per-interview turn ordering

Replaces ordering by fabricated created_at offsets: sequence is the 0-based
insertion order within an interview, unique per (interview_id, sequence).

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("sequence", sa.Integer(), nullable=True))
    # backfill existing rows from their insertion order (created_at carried
    # microsecond offsets precisely to make this ordering unambiguous)
    op.execute(
        """
        UPDATE turns
        SET sequence = numbered.row_index
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY interview_id
                       ORDER BY created_at, id
                   ) - 1 AS row_index
            FROM turns
        ) AS numbered
        WHERE turns.id = numbered.id
        """
    )
    op.alter_column("turns", "sequence", nullable=False)
    op.create_unique_constraint(
        "uq_turns_interview_sequence", "turns", ["interview_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_turns_interview_sequence", "turns", type_="unique")
    op.drop_column("turns", "sequence")
