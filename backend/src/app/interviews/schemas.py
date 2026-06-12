import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.db.models import SessionType
from app.schemas import (
    AnswerKey,
    EvidenceItem,
    InterviewQuestion,
    Profile,
    QuestionType,
    Scores,
)


class CreateInterviewIn(BaseModel):
    jd_text: str = Field(min_length=1)
    resume_text: str | None = None
    session_type: SessionType = SessionType.round


class CreateInterviewOut(BaseModel):
    id: uuid.UUID
    status: Literal["ready", "preparing"]


class InterviewSummaryOut(BaseModel):
    id: uuid.UUID
    status: str
    session_type: SessionType
    # from the parsed profile — null until intake completes
    role: str | None
    seniority: str | None
    question_count: int
    # mean of per-question score averages — null until the interview is judged
    overall_score: float | None
    created_at: datetime
    finished_at: datetime | None


class InterviewListOut(BaseModel):
    interviews: list[InterviewSummaryOut]


class TurnOut(BaseModel):
    id: uuid.UUID
    role: Literal["interviewer", "candidate"]
    content: str
    is_probe: bool
    question_position: int
    created_at: datetime


class InterviewStateOut(BaseModel):
    id: uuid.UUID
    status: str
    session_type: SessionType
    question_count: int
    current_question_position: int | None
    awaiting_answer: bool
    current_question: InterviewQuestion | None
    turns: list[TurnOut]


class AnswerIn(BaseModel):
    text: str = Field(min_length=1)


class EvaluationOut(BaseModel):
    scores: Scores
    evidence: list[EvidenceItem]
    missing_points: list[str]
    model_answer: str
    judge_model: str


class ReportQuestionOut(BaseModel):
    position: int
    qtype: QuestionType
    text: str
    tags: list[str]
    answer_key: AnswerKey
    turns: list[TurnOut]
    evaluation: EvaluationOut


class ReportOut(BaseModel):
    id: uuid.UUID
    status: Literal["complete"]
    profile: Profile
    session_type: SessionType
    finished_at: datetime
    questions: list[ReportQuestionOut]
