"""replace interviews.dev_mode with session_type

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-12 16:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

session_type = sa.Enum("screen", "round", "full_loop", name="session_type")


def upgrade() -> None:
    session_type.create(op.get_bind())
    op.add_column(
        "interviews",
        sa.Column(
            "session_type",
            session_type,
            nullable=False,
            server_default="round",
        ),
    )
    # dev_mode meant 3 questions (now "screen"); everything else was 7
    op.execute(
        "UPDATE interviews SET session_type = "
        "CASE WHEN dev_mode THEN 'screen'::session_type "
        "ELSE 'full_loop'::session_type END"
    )
    op.drop_column("interviews", "dev_mode")


def downgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column(
            "dev_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute("UPDATE interviews SET dev_mode = (session_type = 'screen')")
    op.drop_column("interviews", "session_type")
    session_type.drop(op.get_bind())
