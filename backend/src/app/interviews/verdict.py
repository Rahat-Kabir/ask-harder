"""Synthesizes a hire/no-hire verdict from the per-question scores already in
a report. Pure function of stored data — no LLM call, no new state — so the
product's defining moment ("would you pass?") stays deterministic and testable.
"""

from dataclasses import dataclass, field

from app.interviews.schemas import PracticePriorityOut, VerdictOut
from app.schemas import Scores
from app.skills.service import overall_score, to_hundred

# Pass / borderline thresholds by seniority — the bar rises with the level.
# A senior is expected to clear a higher floor than a junior for the same answer.
_BANDS: dict[str, tuple[float, float]] = {
    "junior": (3.0, 2.2),
    "mid": (3.5, 2.6),
    "senior": (4.0, 3.0),
    "staff": (4.3, 3.3),
    "principal": (4.3, 3.3),
}
# drills and unparseable seniority are judged at the mid bar
_DEFAULT_BAND = _BANDS["mid"]

_DIMENSION_LABELS = {
    "correctness": "correctness",
    "depth": "depth",
    "structure": "structure",
    "communication": "communication",
}


@dataclass
class QuestionResult:
    """The minimum a verdict needs from one judged question."""

    qtype: str
    tags: list[str]
    scores: Scores
    missing_points: list[str] = field(default_factory=list)


def _band_for(seniority: str | None) -> tuple[float, float]:
    if seniority is None:
        return _DEFAULT_BAND
    return _BANDS.get(seniority.strip().lower(), _DEFAULT_BAND)


def _question_label(result: QuestionResult) -> str:
    """Human phrase for a question — its skill tag if it has one, else its type.
    'databases/query-optimization' → 'query optimization'."""
    if result.tags:
        return result.tags[0].split("/")[-1].replace("-", " ")
    return result.qtype.replace("_", " ")


def _weakest_dimension(results: list[QuestionResult]) -> str:
    """The lowest-averaged scoring dimension across the whole interview."""
    totals = {"correctness": 0.0, "depth": 0.0, "structure": 0.0, "communication": 0.0}
    for result in results:
        totals["correctness"] += result.scores.correctness
        totals["depth"] += result.scores.depth
        totals["structure"] += result.scores.structure
        totals["communication"] += result.scores.communication
    weakest = min(totals, key=lambda dim: totals[dim])
    return _DIMENSION_LABELS[weakest]


def _average_overall_score(results: list[QuestionResult]) -> float:
    per_question_scores = [overall_score(result.scores) for result in results]
    return sum(per_question_scores) / len(per_question_scores)


def _practice_priority_reason(
    results: list[QuestionResult],
    score: float,
) -> str:
    weakest_dimension = _weakest_dimension(results).capitalize()
    missing_point_count = sum(len(result.missing_points) for result in results)
    reason = (
        f"Selected because answers in this area averaged {score:g}/100. "
        f"{weakest_dimension} was the weakest dimension"
    )
    if missing_point_count == 1:
        return f"{reason}, and 1 required point was missed."
    if missing_point_count > 1:
        return f"{reason}, and {missing_point_count} required points were missed."
    return f"{reason}."


def build_practice_priorities(
    *,
    decision: str,
    results: list[QuestionResult],
    limit: int = 2,
) -> list[PracticePriorityOut]:
    """Explain the weakest distinct skill tags after a non-passing interview."""
    if decision == "pass" or limit <= 0:
        return []

    results_by_tag: dict[str, list[QuestionResult]] = {}
    for result in results:
        distinct_tags = {raw_tag.strip() for raw_tag in result.tags if raw_tag.strip()}
        for tag in distinct_tags:
            results_by_tag.setdefault(tag, []).append(result)

    ranked_tags = sorted(
        results_by_tag.items(),
        key=lambda item: (_average_overall_score(item[1]), item[0]),
    )

    priorities: list[PracticePriorityOut] = []
    for tag, tagged_results in ranked_tags[:limit]:
        score = to_hundred(_average_overall_score(tagged_results))
        priorities.append(
            PracticePriorityOut(
                tag=tag,
                score=score,
                reason=_practice_priority_reason(tagged_results, score),
            )
        )
    return priorities


def build_verdict(
    *,
    seniority: str | None,
    role: str | None,
    practice_tag: str | None,
    results: list[QuestionResult],
) -> VerdictOut:
    pass_bar, borderline_bar = _band_for(seniority)

    if not results:
        return VerdictOut(
            decision="no",
            headline="No answers to judge.",
            rationale=(
                "Every question was left unanswered, so there is nothing to assess."
            ),
            bar=to_hundred(pass_bar),
            overall=0.0,
        )

    per_question = [overall_score(result.scores) for result in results]
    overall = sum(per_question) / len(per_question)

    if overall >= pass_bar:
        decision = "pass"
    elif overall >= borderline_bar:
        decision = "borderline"
    else:
        decision = "no"

    weakest_index = min(range(len(results)), key=lambda i: per_question[i])
    weakest_label = _question_label(results[weakest_index])
    weakest_score = per_question[weakest_index]
    weakest_dim = _weakest_dimension(results)

    headline = _headline(decision, seniority, role, practice_tag)
    rationale = _rationale(
        decision=decision,
        overall=to_hundred(overall),
        pass_bar=to_hundred(pass_bar),
        borderline_bar=to_hundred(borderline_bar),
        seniority=seniority,
        is_drill=practice_tag is not None,
        weakest_label=weakest_label,
        weakest_score=to_hundred(weakest_score),
        weakest_dim=weakest_dim,
    )

    return VerdictOut(
        decision=decision,
        headline=headline,
        rationale=rationale,
        bar=to_hundred(pass_bar),
        overall=to_hundred(overall),
    )


def _round_label(seniority: str | None, role: str | None) -> str | None:
    if role and seniority:
        return f"{seniority} {role}"
    return None


def _headline(
    decision: str,
    seniority: str | None,
    role: str | None,
    practice_tag: str | None,
) -> str:
    if practice_tag is not None:
        skill = practice_tag.split("/")[-1].replace("-", " ")
        return {
            "pass": f"You're interview-ready on {skill}.",
            "borderline": f"You're close on {skill}, but not there yet.",
            "no": f"You're not ready on {skill} yet.",
        }[decision]

    round_label = _round_label(seniority, role)
    if round_label is not None:
        return {
            "pass": f"You'd likely pass a {round_label} round.",
            "borderline": f"Borderline for a {round_label} round.",
            "no": f"You would not pass a {round_label} round.",
        }[decision]

    return {
        "pass": "You'd likely pass this round.",
        "borderline": "Borderline — not a clear pass.",
        "no": "You would not pass this round.",
    }[decision]


def _rationale(
    *,
    decision: str,
    overall: float,
    pass_bar: float,
    borderline_bar: float,
    seniority: str | None,
    is_drill: bool,
    weakest_label: str,
    weakest_score: float,
    weakest_dim: str,
) -> str:
    level_clause = "" if is_drill or seniority is None else f" for {seniority} level"

    if decision == "no":
        return (
            f"You scored {overall:.0f}/100 against a {pass_bar:.0f} bar{level_clause}. "
            f"Your {weakest_label} answer ({weakest_score:.0f}/100) is what sinks it, "
            f"and {weakest_dim} was your weakest dimension across the interview."
        )
    if decision == "borderline":
        return (
            f"You scored {overall:.0f}/100 — above the {borderline_bar:.0f} floor but "
            f"short of the {pass_bar:.0f} bar for a clear pass. Tighten your "
            f"{weakest_label} answer ({weakest_score:.0f}/100) and your {weakest_dim}, "
            f"and this becomes a yes."
        )
    return (
        f"You scored {overall:.0f}/100, clearing the {pass_bar:.0f} bar. Weakest spot "
        f"was {weakest_label} ({weakest_score:.0f}/100) — worth shoring up, but not a "
        f"blocker."
    )
