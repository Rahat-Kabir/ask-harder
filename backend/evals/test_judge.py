"""The four judge eval suites: ordering, stability, grounding, key adherence.

Stability needs 3 judge runs per answer (60 extra real-model calls on top of
the shared 30), so it carries its own marker — skip it with
`-m "not stability"` when budget matters.
"""

import pytest

from app.llm.judge_common import candidate_transcript, quote_in_transcript
from app.schemas import Evaluation
from evals.conftest import (
    ANSWER_QUALITIES,
    SCORE_DIMENSIONS,
    EvalFixture,
    evaluate_fixture,
    load_fixtures,
    overall_score,
)

pytestmark = pytest.mark.anyio

FIXTURES = load_fixtures()
FIXTURE_IDS = [fixture.name for fixture in FIXTURES]

# at least this share of missing_points must be actual answer-key strings,
# measured across the whole suite
KEY_ADHERENCE_THRESHOLD = 0.8


def test_fixture_set_is_complete():
    assert len(FIXTURES) >= 10
    qtypes = {fixture.question.qtype for fixture in FIXTURES}
    assert len(qtypes) >= 4, f"fixtures only cover qtypes {qtypes}"


# --- Suite 1: ordering ------------------------------------------------------


@pytest.mark.parametrize("fixture", FIXTURES, ids=FIXTURE_IDS)
async def test_score_ordering(fixture: EvalFixture):
    overall: dict[str, float] = {}
    for quality in ANSWER_QUALITIES:
        evaluation = await evaluate_fixture(fixture, quality)
        overall[quality] = overall_score(evaluation)
    assert overall["bad"] < overall["mediocre"] < overall["strong"], (
        f"ordering broken on {fixture.name}: {overall}"
    )


# --- Suite 2: stability -----------------------------------------------------

STABILITY_RUNS = 3
# per-dimension spread ≤ ±0.5 across runs, i.e. max-min ≤ 1
MAX_DIMENSION_SPREAD = 1


@pytest.mark.stability
@pytest.mark.parametrize("quality", ANSWER_QUALITIES)
@pytest.mark.parametrize("fixture", FIXTURES, ids=FIXTURE_IDS)
async def test_score_stability(fixture: EvalFixture, quality: str):
    evaluations: list[Evaluation] = [
        await evaluate_fixture(fixture, quality, run=run_index)
        for run_index in range(STABILITY_RUNS)
    ]
    for dimension in SCORE_DIMENSIONS:
        values = [
            getattr(evaluation.scores, dimension) for evaluation in evaluations
        ]
        assert max(values) - min(values) <= MAX_DIMENSION_SPREAD, (
            f"unstable {dimension} on {fixture.name}/{quality}: {values}"
        )


# --- Suite 3: grounding ---------------------------------------------------


@pytest.mark.parametrize("quality", ANSWER_QUALITIES)
@pytest.mark.parametrize("fixture", FIXTURES, ids=FIXTURE_IDS)
async def test_evidence_quotes_are_verbatim(fixture: EvalFixture, quality: str):
    evaluation = await evaluate_fixture(fixture, quality)
    transcript = candidate_transcript(fixture.turns(quality))
    for item in evaluation.evidence:
        assert quote_in_transcript(item.quote, transcript), (
            f"ungrounded quote on {fixture.name}/{quality}: {item.quote!r}"
        )


@pytest.mark.parametrize("fixture", FIXTURES, ids=FIXTURE_IDS)
async def test_strong_answers_yield_evidence(fixture: EvalFixture):
    # non-triviality guard: a judge that cites nothing would pass the
    # verbatim check vacuously
    evaluation = await evaluate_fixture(fixture, "strong")
    assert evaluation.evidence, f"no evidence cited on {fixture.name}/strong"


# --- Suite 4: key adherence -----------------------------------------------


async def test_missing_points_adhere_to_answer_keys():
    total_points = 0
    matched_points = 0
    unmatched: list[str] = []
    for fixture in FIXTURES:
        allowed = set(fixture.question.answer_key.required_points) | set(
            fixture.question.answer_key.strong_signals
        )
        for quality in ANSWER_QUALITIES:
            evaluation = await evaluate_fixture(fixture, quality)
            for point in evaluation.missing_points:
                total_points += 1
                if point in allowed:
                    matched_points += 1
                else:
                    unmatched.append(f"{fixture.name}/{quality}: {point!r}")

    assert total_points > 0, "judge never reported a missing point"
    adherence = matched_points / total_points
    assert adherence >= KEY_ADHERENCE_THRESHOLD, (
        f"key adherence {adherence:.0%} < {KEY_ADHERENCE_THRESHOLD:.0%}; "
        f"invented points:\n" + "\n".join(unmatched)
    )


@pytest.mark.parametrize("fixture", FIXTURES, ids=FIXTURE_IDS)
async def test_bad_answers_have_missing_points(fixture: EvalFixture):
    # non-triviality guard: a bad answer must miss something, or the judge
    # is too kind to be useful
    evaluation = await evaluate_fixture(fixture, "bad")
    assert evaluation.missing_points, (
        f"judge found nothing missing in {fixture.name}/bad"
    )
