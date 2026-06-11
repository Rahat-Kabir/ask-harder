"""The four LLM components, as structural interfaces.

Every component has at least two implementations: a real provider-backed one
and the MockBackend. Callers depend on these protocols only — provider
selection is config, not code.
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.schemas import (
    Evaluation,
    InterviewerReply,
    InterviewQuestion,
    Plan,
    PlannedQuestion,
    Profile,
    Turn,
)


@runtime_checkable
class IntakeParser(Protocol):
    async def parse(self, jd_text: str, resume_text: str | None = None) -> Profile: ...


@runtime_checkable
class PlanGenerator(Protocol):
    async def generate(
        self,
        profile: Profile,
        skill_profile: dict[str, float],
        n_questions: int,
    ) -> Plan: ...


@runtime_checkable
class Interviewer(Protocol):
    """Context starvation by design: gets ONE key-less question and ITS
    turns — never the answer key, never other questions, never the full
    interview. `probes_left` is state-machine truth the prompt may repeat;
    the backend enforces the cap regardless of what the model returns."""

    async def respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> InterviewerReply: ...

    def stream_respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class Judge(Protocol):
    """Never talks to the user; one call per question."""

    async def evaluate(
        self,
        question: PlannedQuestion,
        turns: list[Turn],
    ) -> Evaluation: ...
