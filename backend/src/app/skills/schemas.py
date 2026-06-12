import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas import EvidenceItem, QuestionType, Scores


class SkillOut(BaseModel):
    tag: str
    average: float = Field(ge=1.0, le=5.0)
    evaluation_count: int = Field(ge=1)
    updated_at: datetime
    # latest-interview average minus the previous interview's on this tag;
    # null until the tag has been judged in two interviews
    trend: float | None = None


class SkillsOut(BaseModel):
    skills: list[SkillOut]


class SkillAnswerOut(BaseModel):
    """One judged answer on this tag — the receipts behind the average."""

    interview_id: uuid.UUID
    interview_created_at: datetime
    position: int
    qtype: QuestionType
    question_text: str
    # what the candidate said, in turn order (probe replies included)
    candidate_answers: list[str]
    scores: Scores
    evidence: list[EvidenceItem]
    missing_points: list[str]
    judge_model: str


class SkillDetailOut(BaseModel):
    tag: str
    average: float = Field(ge=1.0, le=5.0)
    evaluation_count: int = Field(ge=1)
    answers: list[SkillAnswerOut]
