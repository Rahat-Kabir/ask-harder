"""Deterministic verdict synthesis — no DB, no LLM."""

from app.interviews.verdict import QuestionResult, build_verdict
from app.schemas import Scores


def _result(score: int, tags: list[str] | None = None, qtype: str = "technical"):
    return QuestionResult(
        qtype=qtype,
        tags=tags if tags is not None else ["databases/query-optimization"],
        scores=Scores(
            correctness=score, depth=score, structure=score, communication=score
        ),
    )


def test_strong_interview_passes_at_mid():
    verdict = build_verdict(
        seniority="mid",
        role="Backend Engineer",
        practice_tag=None,
        results=[_result(4), _result(4), _result(4)],
    )
    assert verdict.decision == "pass"
    assert verdict.bar == 3.5
    assert verdict.overall == 4.0
    assert "Backend Engineer" in verdict.headline


def test_same_scores_fail_at_senior_bar():
    # 3.5 average clears mid (3.5) but not senior (4.0)
    results = [_result(4), _result(4), _result(3)]
    mid = build_verdict(
        seniority="mid", role="Backend Engineer", practice_tag=None, results=results
    )
    senior = build_verdict(
        seniority="senior", role="Backend Engineer", practice_tag=None, results=results
    )
    assert mid.decision == "pass"
    assert senior.decision in {"borderline", "no"}
    assert senior.bar == 4.0


def test_weak_interview_is_a_no():
    verdict = build_verdict(
        seniority="senior",
        role="Backend Engineer",
        practice_tag=None,
        results=[_result(2), _result(1), _result(2)],
    )
    assert verdict.decision == "no"
    assert "would not pass" in verdict.headline.lower()


def test_borderline_band():
    # mid: pass 3.5, borderline floor 2.6 — a 3.0 average lands borderline
    verdict = build_verdict(
        seniority="mid",
        role="Backend Engineer",
        practice_tag=None,
        results=[_result(3), _result(3), _result(3)],
    )
    assert verdict.decision == "borderline"


def test_rationale_names_weakest_question_and_dimension():
    # a failing interview where rate-limiting is the weakest question and
    # depth is the weakest dimension overall — both should be named
    results = [
        QuestionResult(
            qtype="technical",
            tags=["systems/api-design"],
            scores=Scores(correctness=3, depth=2, structure=3, communication=3),
        ),
        QuestionResult(
            qtype="technical",
            tags=["systems/rate-limiting"],
            scores=Scores(correctness=1, depth=1, structure=2, communication=2),
        ),
        QuestionResult(
            qtype="technical",
            tags=["databases/indexing"],
            scores=Scores(correctness=3, depth=2, structure=3, communication=3),
        ),
    ]
    verdict = build_verdict(
        seniority="mid", role="Backend Engineer", practice_tag=None, results=results
    )
    assert verdict.decision == "no"
    assert "rate limiting" in verdict.rationale
    # depth is the lowest dimension overall, so it should be called out
    assert "depth" in verdict.rationale


def test_drill_uses_skill_framing_not_role():
    verdict = build_verdict(
        seniority=None,
        role=None,
        practice_tag="behavioral/ownership",
        results=[_result(1, tags=["behavioral/ownership"])],
    )
    assert "ownership" in verdict.headline
    assert "round" not in verdict.headline
    # drills are judged at the mid bar
    assert verdict.bar == 3.5


def test_empty_results_is_a_no():
    verdict = build_verdict(
        seniority="mid", role="Backend Engineer", practice_tag=None, results=[]
    )
    assert verdict.decision == "no"
    assert verdict.overall == 0.0


def test_unknown_seniority_falls_back_to_mid_bar():
    verdict = build_verdict(
        seniority="wizard",
        role="Backend Engineer",
        practice_tag=None,
        results=[_result(4), _result(4), _result(4)],
    )
    assert verdict.bar == 3.5
