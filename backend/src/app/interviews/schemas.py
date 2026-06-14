import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    # exactly one of jd_text / practice_tag: a JD interview or a skill drill
    jd_text: str | None = Field(default=None, min_length=1)
    practice_tag: str | None = Field(default=None, min_length=1)
    resume_text: str | None = None
    session_type: SessionType = SessionType.round

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "CreateInterviewIn":
        if (self.jd_text is None) == (self.practice_tag is None):
            raise ValueError("Provide exactly one of jd_text or practice_tag")
        return self


class CreateInterviewOut(BaseModel):
    id: uuid.UUID
    status: Literal["ready", "preparing"]


class QuotaOut(BaseModel):
    limit: int
    used_today: int
    remaining: int
    resets_at: datetime


class InterviewSummaryOut(BaseModel):
    id: uuid.UUID
    status: str
    session_type: SessionType
    # set for skill drills; role/seniority stay null for those
    practice_tag: str | None
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
    is_skip: bool
    question_position: int
    created_at: datetime


class InterviewStateOut(BaseModel):
    id: uuid.UUID
    status: str
    session_type: SessionType
    practice_tag: str | None
    # what intake parsed from the JD — shown for confirmation before the
    # interview starts; null for practice drills and while preparing
    profile: Profile | None
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


class VerdictOut(BaseModel):
    # the product's defining moment — would you pass this round?
    decision: Literal["pass", "borderline", "no"]
    headline: str
    rationale: str
    # the pass threshold used (rises with seniority) and the achieved average,
    # both surfaced so the call is transparent, not a black box
    bar: float
    overall: float


class ReportOut(BaseModel):
    id: uuid.UUID
    status: Literal["complete"]
    # null for practice drills — there is no JD to parse
    profile: Profile | None
    practice_tag: str | None
    session_type: SessionType
    finished_at: datetime
    verdict: VerdictOut
    questions: list[ReportQuestionOut]
