"""LLM component I/O types — every model input/output is one of these.

No raw-string parsing of model output anywhere: real backends must produce
these types (or fail validation), and the rest of the app only ever sees
validated data. The mock and real backends are interchangeable behind them.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    warmup = "warmup"
    behavioral = "behavioral"
    technical = "technical"
    system_design = "system_design"


class Profile(BaseModel):
    """IntakeParser output: what the JD (and resume) say about the target."""

    role: str
    seniority: str
    stack: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    # concrete, probeable resume claims ("scaled API to 10k req/s")
    resume_claims: list[str] = Field(default_factory=list)


class AnswerKey(BaseModel):
    """Frozen at plan time — the judge's only ground truth."""

    required_points: list[str]
    strong_signals: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class InterviewQuestion(BaseModel):
    """What the interviewer (and the candidate) are allowed to see.

    Deliberately has NO answer_key field: the Interviewer interface takes
    this type, so a leak of the key into an interviewer prompt is a type
    error, not a code-review hope.
    """

    position: int
    qtype: QuestionType
    text: str


class PlannedQuestion(InterviewQuestion):
    """Full planner output — the judge's view. Never sent to the client
    until the report."""

    tags: list[str] = Field(default_factory=list)
    answer_key: AnswerKey

    def public(self) -> InterviewQuestion:
        return InterviewQuestion(
            position=self.position, qtype=self.qtype, text=self.text
        )


class Plan(BaseModel):
    """PlanGenerator output."""

    questions: list[PlannedQuestion]


class Turn(BaseModel):
    """One utterance within a single question's exchange."""

    role: Literal["interviewer", "candidate"]
    content: str


class InterviewerReply(BaseModel):
    """Either a follow-up probe to say out loud, or a done signal.

    The model only *suggests*; the backend state machine decides what
    actually happens (probe caps, advancing, ending).
    """

    done: bool = False
    text: str | None = None


class Scores(BaseModel):
    correctness: int = Field(ge=1, le=5)
    depth: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)


class EvidenceItem(BaseModel):
    claim: str
    # must be verbatim from the candidate's turns — validated in code after
    # every judge call, not trusted from the model
    quote: str


class Evaluation(BaseModel):
    """Judge output for one question."""

    scores: Scores
    evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    model_answer: str
