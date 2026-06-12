"""Mix real and mock LLM components behind one backend object."""

from app.llm.interfaces import IntakeParser, Interviewer, Judge, PlanGenerator
from app.schemas import (
    Evaluation,
    InterviewerReply,
    InterviewQuestion,
    Plan,
    PlannedQuestion,
    Profile,
    Turn,
)


class CompositeLlmBackend:
    """Real intake/plan/interviewer/judge via provider-backed components."""

    def __init__(
        self,
        intake: IntakeParser,
        planner: PlanGenerator,
        interviewer: Interviewer,
        judge: Judge,
    ) -> None:
        self._intake = intake
        self._planner = planner
        self._interviewer = interviewer
        self._judge = judge

    @property
    def judge_model_name(self) -> str:
        return getattr(self._judge, "judge_model_name", "unknown")

    async def parse(self, jd_text: str, resume_text: str | None = None) -> Profile:
        return await self._intake.parse(jd_text, resume_text)

    async def generate(
        self,
        profile: Profile,
        skill_profile: dict[str, float],
        n_questions: int,
    ) -> Plan:
        return await self._planner.generate(profile, skill_profile, n_questions)

    async def generate_practice(
        self,
        tag: str,
        average: float | None,
        n_questions: int,
    ) -> Plan:
        return await self._planner.generate_practice(tag, average, n_questions)

    async def respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> InterviewerReply:
        return await self._interviewer.respond(question, turns, probes_left)

    def stream_respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ):
        return self._interviewer.stream_respond(question, turns, probes_left)

    async def evaluate(
        self,
        question: PlannedQuestion,
        turns: list[Turn],
    ) -> Evaluation:
        return await self._judge.evaluate(question, turns)
