"""MockBackend: deterministic stand-in for all four LLM components.

Runs the full interview flow without external API calls — used for tests
and local development. Same inputs always produce the same outputs.
"""

from collections.abc import AsyncIterator

from app.schemas import (
    AnswerKey,
    Evaluation,
    EvidenceItem,
    InterviewerReply,
    InterviewQuestion,
    Plan,
    PlannedQuestion,
    Profile,
    QuestionType,
    Scores,
    Turn,
)

_QUESTION_BANK: list[PlannedQuestion] = [
    PlannedQuestion(
        position=0,
        qtype=QuestionType.warmup,
        text="Walk me through a recent project you are proud of. What was your role?",
        tags=["behavioral/ownership"],
        answer_key=AnswerKey(
            required_points=[
                "Names a concrete project and their specific role",
                "States the outcome or impact",
            ],
            strong_signals=["Quantifies impact"],
            red_flags=["Cannot name own contribution"],
        ),
    ),
    PlannedQuestion(
        position=1,
        qtype=QuestionType.technical,
        text="What does a database index actually do, and when would adding one hurt?",
        tags=["databases/indexing"],
        answer_key=AnswerKey(
            required_points=[
                "Index trades read speed for write cost and storage",
                "B-tree (or similar) lookup instead of full scan",
                "Hurts on write-heavy tables or low-selectivity columns",
            ],
            strong_signals=["Mentions covering indexes or selectivity"],
            red_flags=["Indexes make everything faster"],
        ),
    ),
    PlannedQuestion(
        position=2,
        qtype=QuestionType.system_design,
        text="Design a rate limiter for a public API. Sketch the approach.",
        tags=["system_design/rate-limiting"],
        answer_key=AnswerKey(
            required_points=[
                "Picks an algorithm (token bucket / sliding window) and says why",
                "Identifies where state lives (per-node vs shared store)",
                "Mentions failure behavior (fail-open vs fail-closed)",
            ],
            strong_signals=["Discusses distributed coordination trade-offs"],
            red_flags=["No mention of state location"],
        ),
    ),
]


class MockBackend:
    judge_model_name = "mock"
    """Implements IntakeParser, PlanGenerator, Interviewer and Judge."""

    async def parse(self, jd_text: str, resume_text: str | None = None) -> Profile:
        # Keyword-based profile extraction for deterministic mock intake
        text = jd_text.lower()
        stack = [
            tech
            for tech in ("python", "fastapi", "postgres", "react", "docker", "aws")
            if tech in text
        ]
        seniority = "senior" if "senior" in text else "mid"
        resume_claims = []
        if resume_text:
            # first non-empty lines stand in for extracted claims
            resume_claims = [
                line.strip() for line in resume_text.splitlines() if line.strip()
            ][:3]
        return Profile(
            role="Backend Engineer",
            seniority=seniority,
            stack=stack or ["python"],
            competencies=["api-design", "databases", "system-design"],
            resume_claims=resume_claims,
        )

    async def generate(
        self,
        profile: Profile,
        skill_profile: dict[str, float],
        n_questions: int,
    ) -> Plan:
        bank = _QUESTION_BANK
        questions = [
            question.model_copy(update={"position": idx})
            for idx, question in enumerate(
                (bank * (n_questions // len(bank) + 1))[:n_questions]
            )
        ]
        return Plan(questions=questions)

    async def generate_practice(
        self,
        tag: str,
        average: float | None,
        n_questions: int,
    ) -> Plan:
        # bank questions re-tagged to the drilled skill — deterministic,
        # and every judged answer feeds the tag being practiced
        bank = _QUESTION_BANK
        questions = [
            question.model_copy(update={"position": idx, "tags": [tag]})
            for idx, question in enumerate(
                (bank * (n_questions // len(bank) + 1))[:n_questions]
            )
        ]
        return Plan(questions=questions)

    async def respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> InterviewerReply:
        candidate_answers = [t for t in turns if t.role == "candidate"]
        if not candidate_answers:
            # nothing to probe yet; the state machine shouldn't call us here,
            # but answer sanely anyway
            return InterviewerReply(text=question.text)
        if probes_left > 0 and len(candidate_answers) == 1:
            return InterviewerReply(
                text="Can you give a concrete example of that — "
                "what did you actually do?"
            )
        return InterviewerReply(done=True)

    async def stream_respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> AsyncIterator[str]:
        reply = await self.respond(question, turns, probes_left)
        if reply.text:
            yield reply.text

    async def evaluate(
        self,
        question: PlannedQuestion,
        turns: list[Turn],
    ) -> Evaluation:
        candidate_text = " ".join(
            t.content for t in turns if t.role == "candidate"
        ).strip()
        # longer answers score better — a transparent, deterministic stand-in
        # for real judging, good enough to exercise report UI ranges. Bands
        # chosen so the eval fixtures' bad/mediocre/strong answers land in
        # distinct levels (bads run up to ~35 words, mediocres up to ~90).
        word_count = len(candidate_text.split())
        level = 2 if word_count < 40 else 3 if word_count < 120 else 4

        # quote must be verbatim from the transcript — the mock honors the
        # same grounding contract the real judge is validated against
        first_candidate_turn = next(
            (t.content for t in turns if t.role == "candidate"), ""
        )
        quote = first_candidate_turn[:120]
        missing = question.answer_key.required_points[level - 1 :]
        evidence: list[EvidenceItem] = []
        if quote:
            evidence.append(
                EvidenceItem(
                    claim="Opening of the candidate's answer",
                    quote=quote,
                    supports=True,
                )
            )
            # exercise the gap polarity whenever the answer left points unmet
            if missing and len(first_candidate_turn) > 60:
                evidence.append(
                    EvidenceItem(
                        claim="Trails off without covering the rubric",
                        quote=first_candidate_turn[-60:],
                        supports=False,
                    )
                )
        return Evaluation(
            scores=Scores(
                correctness=level,
                depth=max(level - 1, 1),
                structure=level,
                communication=min(level + 1, 5),
            ),
            evidence=evidence,
            missing_points=list(missing),
            model_answer=(
                "A strong answer would cover: "
                + "; ".join(question.answer_key.required_points)
                + "."
            ),
        )
