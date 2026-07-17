"""Deterministic verdict synthesis — no DB, no LLM."""

from app.interviews.verdict import (
    QuestionResult,
    build_practice_priorities,
    build_verdict,
)
from app.schemas import Scores


def _result(
    score: int,
    tags: list[str] | None = None,
    qtype: str = "technical",
    missing_points: list[str] | None = None,
):
    return QuestionResult(
        qtype=qtype,
        tags=tags if tags is not None else ["databases/query-optimization"],
        scores=Scores(
            correctness=score, depth=score, structure=score, communication=score
        ),
        missing_points=missing_points or [],
    )


def test_strong_interview_passes_at_mid():
    verdict = build_verdict(
        seniority="mid",
        role="Backend Engineer",
        practice_tag=None,
        results=[_result(4), _result(4), _result(4)],
    )
    assert verdict.decision == "pass"
    # 1-5 bars/scores surface on the 0-100 scale: 3.5->62.5, 4.0->75.0
    assert verdict.bar == 62.5
    assert verdict.overall == 75.0
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
    assert senior.bar == 75.0


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
    # drills are judged at the mid bar (3.5 -> 62.5 on the 0-100 scale)
    assert verdict.bar == 62.5


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
    assert verdict.bar == 62.5


def test_practice_priorities_select_two_weakest_distinct_tags():
    priorities = build_practice_priorities(
        decision="no",
        results=[
            _result(4, tags=["systems/api-design"]),
            _result(
                1,
                tags=["databases/indexing", "databases/indexing"],
                missing_points=["index selectivity"],
            ),
            _result(2, tags=["security/authentication"]),
        ],
    )

    assert [priority.tag for priority in priorities] == [
        "databases/indexing",
        "security/authentication",
    ]
    assert [priority.score for priority in priorities] == [0.0, 25.0]


def test_practice_priority_aggregates_repeated_tag_and_explains_selection():
    priorities = build_practice_priorities(
        decision="borderline",
        limit=1,
        results=[
            QuestionResult(
                qtype="technical",
                tags=["databases/indexing"],
                scores=Scores(
                    correctness=3,
                    depth=1,
                    structure=2,
                    communication=3,
                ),
                missing_points=["index selectivity", "query plan"],
            ),
            QuestionResult(
                qtype="system_design",
                tags=["databases/indexing"],
                scores=Scores(
                    correctness=5,
                    depth=3,
                    structure=4,
                    communication=5,
                ),
            ),
        ],
    )

    assert len(priorities) == 1
    assert priorities[0].tag == "databases/indexing"
    assert priorities[0].score == 56.2
    assert "Depth was the weakest dimension" in priorities[0].reason
    assert "2 required points were missed" in priorities[0].reason


def test_practice_priorities_handle_passes_and_missing_tags():
    assert (
        build_practice_priorities(
            decision="pass",
            results=[_result(2, tags=["databases/indexing"])],
        )
        == []
    )
    assert (
        build_practice_priorities(
            decision="no",
            results=[_result(1, tags=[])],
        )
        == []
    )
