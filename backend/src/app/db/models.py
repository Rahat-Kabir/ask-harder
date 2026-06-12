import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.schemas import QuestionType


class InterviewStatus(enum.StrEnum):
    preparing = "preparing"
    ready = "ready"
    in_progress = "in_progress"
    judging = "judging"
    complete = "complete"
    abandoned = "abandoned"


class TurnRole(enum.StrEnum):
    interviewer = "interviewer"
    candidate = "candidate"


class SessionType(enum.StrEnum):
    """Interview length, named like real hiring stages."""

    screen = "screen"  # 3 questions — quick readiness check
    round = "round"  # 5 questions — the default
    full_loop = "full_loop"  # 7 questions — pre-interview stress test


class User(Base):
    __tablename__ = "users"

    # UUIDs (not serial ints) because ids end up in URLs — non-guessable,
    # and they don't leak how many users exist.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # saved once, auto-filled into the intake form on every interview
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # sha256 of the cookie token — a leaked DB dump must not contain usable
    # session tokens
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, name="interview_status"),
        default=InterviewStatus.preparing,
    )
    jd_text: Mapped[str] = mapped_column(Text, default="")
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # set instead of jd_text for practice drills — the interview targets
    # one skill tag and skips intake parsing entirely
    practice_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, name="session_type"), default=SessionType.round
    )
    # set when the interview starts; indexes into the ordered questions list
    current_question_position: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # soft delete: hidden everywhere user-facing, but the row keeps its
    # quota slot — a hard delete would allow create→delete→create loops
    # around the daily limit
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "position", name="uq_questions_interview_position"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    qtype: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type")
    )
    text: Mapped[str] = mapped_column(Text)
    # frozen at plan time — never sent to the client until the report
    answer_key_json: Mapped[dict] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class InterviewTurn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint(
            "interview_id", "sequence", name="uq_turns_interview_sequence"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )
    # 0-based insertion order within the interview — the one true turn
    # ordering; created_at ties when several turns land in one transaction
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[TurnRole] = mapped_column(Enum(TurnRole, name="turn_role"))
    content: Mapped[str] = mapped_column(Text)
    is_probe: Mapped[bool] = mapped_column(Boolean, default=False)
    # candidate bailed instead of answering — a different fact than a bad
    # answer; fully-skipped questions are judged deterministically, not by LLM
    is_skip: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuestionEvaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )
    scores_json: Mapped[dict] = mapped_column(JSONB)
    evidence_json: Mapped[list] = mapped_column(JSONB)
    missing_points_json: Mapped[list] = mapped_column(JSONB)
    model_answer: Mapped[str] = mapped_column(Text)
    judge_model: Mapped[str] = mapped_column(String(64), default="mock")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SkillScore(Base):
    __tablename__ = "skill_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "tag", name="uq_skill_scores_user_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    tag: Mapped[str] = mapped_column(Text)
    # running sum + count — average computed on read for exact rolling means
    score_sum: Mapped[float] = mapped_column()
    evaluation_count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
