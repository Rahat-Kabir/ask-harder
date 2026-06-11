"""interview tables

Revision ID: a1b2c3d4e5f6
Revises: 579f5fdae7c5
Create Date: 2026-06-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "579f5fdae7c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

interview_status = postgresql.ENUM(
    "preparing",
    "ready",
    "in_progress",
    "judging",
    "complete",
    "abandoned",
    name="interview_status",
    create_type=False,
)
question_type = postgresql.ENUM(
    "warmup",
    "behavioral",
    "technical",
    "system_design",
    name="question_type",
    create_type=False,
)
turn_role = postgresql.ENUM(
    "interviewer",
    "candidate",
    name="turn_role",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    interview_status.create(op.get_bind(), checkfirst=True)
    question_type.create(op.get_bind(), checkfirst=True)
    turn_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "interviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            interview_status,
            nullable=False,
            server_default="preparing",
        ),
        sa.Column("jd_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("profile_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dev_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_question_position", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_interviews_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("qtype", question_type, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answer_key_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_questions_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        sa.UniqueConstraint(
            "interview_id",
            "position",
            name=op.f("uq_questions_interview_position"),
        ),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("role", turn_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_probe", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_turns_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_turns_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turns")),
    )
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("scores_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "missing_points_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("model_answer", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.String(length=64), nullable=False, server_default="mock"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_evaluations_interview_id_interviews"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_evaluations_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluations")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("evaluations")
    op.drop_table("turns")
    op.drop_table("questions")
    op.drop_table("interviews")
    turn_role.drop(op.get_bind(), checkfirst=True)
    question_type.drop(op.get_bind(), checkfirst=True)
    interview_status.drop(op.get_bind(), checkfirst=True)
