"""Contract tests: MockBackend must honor the same invariants the real
backends will be held to — so the rest of the app can't tell them apart."""

import pytest

from app.llm.interfaces import IntakeParser, Interviewer, Judge, PlanGenerator
from app.llm.mock import MockBackend
from app.schemas import Turn

pytestmark = pytest.mark.anyio

JD = "Senior Backend Engineer: Python, FastAPI, Postgres. Owns API design."


def test_mock_satisfies_all_four_interfaces():
    backend = MockBackend()
    assert isinstance(backend, IntakeParser)
    assert isinstance(backend, PlanGenerator)
    assert isinstance(backend, Interviewer)
    assert isinstance(backend, Judge)


async def test_parse_extracts_stack_and_claims():
    profile = await MockBackend().parse(JD, resume_text="Scaled API to 10k req/s")
    assert profile.seniority == "senior"
    assert "python" in profile.stack
    assert profile.resume_claims == ["Scaled API to 10k req/s"]


async def test_plan_has_n_ordered_questions_with_keys():
    backend = MockBackend()
    profile = await backend.parse(JD)
    plan = await backend.generate(profile, skill_profile={}, n_questions=3)

    assert len(plan.questions) == 3
    assert [q.position for q in plan.questions] == [0, 1, 2]
    assert all(q.answer_key.required_points for q in plan.questions)


async def test_interviewer_probes_once_then_signals_done():
    backend = MockBackend()
    plan = await backend.generate(await backend.parse(JD), {}, 1)
    question = plan.questions[0].public()

    turns: list[Turn] = [
        Turn(role="interviewer", content=question.text),
        Turn(role="candidate", content="I built a thing once."),
    ]
    probe = await backend.respond(question, turns, probes_left=2)
    assert not probe.done
    assert probe.text

    turns += [
        Turn(role="interviewer", content=probe.text),
        Turn(role="candidate", content="Concretely, I designed the API layer."),
    ]
    reply = await backend.respond(question, turns, probes_left=1)
    assert reply.done


async def test_interviewer_respects_zero_probes_left():
    backend = MockBackend()
    plan = await backend.generate(await backend.parse(JD), {}, 1)
    question = plan.questions[0].public()
    turns = [
        Turn(role="interviewer", content=question.text),
        Turn(role="candidate", content="Short answer."),
    ]
    reply = await backend.respond(question, turns, probes_left=0)
    assert reply.done


async def test_judge_evidence_quotes_are_verbatim_from_transcript():
    backend = MockBackend()
    plan = await backend.generate(await backend.parse(JD), {}, 1)
    question = plan.questions[0]

    answer = (
        "I led the migration of our monolith to services. I owned the API "
        "gateway, set the SLOs, and cut p99 latency by 40 percent over a "
        "two-quarter rollout with three engineers reporting to me."
    )
    turns = [
        Turn(role="interviewer", content=question.text),
        Turn(role="candidate", content=answer),
    ]
    evaluation = await backend.evaluate(question, turns)

    transcript = " ".join(t.content for t in turns if t.role == "candidate")
    for item in evaluation.evidence:
        assert item.quote in transcript

    # missing points must come from the frozen key, not be invented
    for point in evaluation.missing_points:
        assert point in question.answer_key.required_points


async def test_judge_scores_track_answer_quality():
    """Ordering: a weak answer must not outscore a strong one (mock keeps
    the same property the real judge is eval-harnessed for)."""
    backend = MockBackend()
    plan = await backend.generate(await backend.parse(JD), {}, 1)
    question = plan.questions[0]

    def turns_for(answer: str) -> list[Turn]:
        return [
            Turn(role="interviewer", content=question.text),
            Turn(role="candidate", content=answer),
        ]

    weak = await backend.evaluate(question, turns_for("I did some backend work."))
    strong = await backend.evaluate(
        question,
        turns_for(
            "I led the migration of our checkout monolith into four services "
            "over two quarters. I owned the payments API: defined the contract, "
            "wrote the gateway routing, added idempotency keys, and set up "
            "shadow traffic to validate parity before cutover. Result: p99 "
            "latency dropped 40 percent and deploy frequency tripled. My role "
            "specifically was tech lead for three engineers; I wrote the "
            "design doc, reviewed every interface change, and ran the rollout."
        ),
    )
    assert strong.scores.correctness > weak.scores.correctness
