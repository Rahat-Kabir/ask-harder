"""Eval harness setup — no database, no app server, just judge + fixtures.

Judge selection is by env var so the same suite runs with no API keys (mock, the
default — proves the harness plumbing) or against the real model:

    uv run pytest evals                          # mock judge, free
    EVAL_JUDGE=anthropic uv run pytest evals     # real Sonnet judge

Evals call the judge's *raw* output (evaluate_raw when available): the
production evaluate() pipeline strips ungrounded evidence and filters
missing_points, which would make these assertions true by construction.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

import pytest

from app.schemas import AnswerKey, Evaluation, PlannedQuestion, Turn

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ANSWER_QUALITIES = ("bad", "mediocre", "strong")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@dataclass(frozen=True)
class EvalFixture:
    name: str
    question: PlannedQuestion
    # quality ("bad" | "mediocre" | "strong") -> answer text
    answers: dict[str, str]

    def turns(self, quality: str) -> list[Turn]:
        return [
            Turn(role="interviewer", content=self.question.text),
            Turn(role="candidate", content=self.answers[quality]),
        ]


def load_fixtures() -> list[EvalFixture]:
    fixtures = []
    for fixture_dir in sorted(FIXTURES_DIR.iterdir()):
        if not fixture_dir.is_dir():
            continue
        question_data = json.loads(
            (fixture_dir / "question.json").read_text(encoding="utf-8")
        )
        key_data = json.loads(
            (fixture_dir / "answer_key.json").read_text(encoding="utf-8")
        )
        question = PlannedQuestion(**question_data, answer_key=AnswerKey(**key_data))
        answers = {
            quality: (fixture_dir / f"answer_{quality}.txt").read_text(encoding="utf-8")
            for quality in ANSWER_QUALITIES
        }
        fixtures.append(
            EvalFixture(name=fixture_dir.name, question=question, answers=answers)
        )
    return fixtures


def make_judge():
    backend = os.environ.get("EVAL_JUDGE", "mock")
    if backend == "mock":
        from app.llm.mock import MockBackend

        return MockBackend()
    if backend == "anthropic":
        from app.config import settings
        from app.llm.judge import AnthropicJudge

        if not settings.anthropic_api_key:
            raise RuntimeError("EVAL_JUDGE=anthropic requires ANTHROPIC_API_KEY")
        return AnthropicJudge(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_judge_model,
            max_tokens=settings.anthropic_judge_max_tokens,
        )
    raise RuntimeError(f"Unknown EVAL_JUDGE: {backend!r}")


# One judge call per (fixture, quality, run) for the whole session — every
# suite reads from here, so run 0 is shared by ordering/grounding/adherence
# and only the stability suite pays for runs 1..N-1.
_evaluation_cache: dict[tuple[str, str, int], Evaluation] = {}


async def evaluate_fixture(
    fixture: EvalFixture, quality: str, run: int = 0
) -> Evaluation:
    cache_key = (fixture.name, quality, run)
    if cache_key not in _evaluation_cache:
        # judge clients hold event-loop-bound resources and anyio gives each
        # test a fresh loop, so build the judge per call; only results cache
        judge = make_judge()
        raw_evaluate = getattr(judge, "evaluate_raw", judge.evaluate)
        _evaluation_cache[cache_key] = await raw_evaluate(
            fixture.question, fixture.turns(quality)
        )
    return _evaluation_cache[cache_key]


# --- Results artifact ------------------------------------------------------
# Every eval session dumps its raw-output metrics to evals/results/<judge>.json.
# This is the data the public /methodology page will render — committed to the
# repo, so a paid run's findings outlive the run.

RESULTS_DIR = Path(__file__).parent / "results"

SCORE_DIMENSIONS = ("correctness", "depth", "structure", "communication")


def overall_score(evaluation: Evaluation) -> float:
    return sum(
        getattr(evaluation.scores, dimension) for dimension in SCORE_DIMENSIONS
    ) / len(SCORE_DIMENSIONS)


def _build_report() -> dict:
    from datetime import datetime

    from app.llm.judge_common import candidate_transcript, quote_in_transcript

    fixtures_by_name = {fixture.name: fixture for fixture in load_fixtures()}

    quotes_total = quotes_grounded = 0
    points_total = points_matched = 0
    per_fixture: dict[str, dict] = {}

    for (fixture_name, quality, run), evaluation in _evaluation_cache.items():
        fixture = fixtures_by_name[fixture_name]
        transcript = candidate_transcript(fixture.turns(quality))
        for item in evaluation.evidence:
            quotes_total += 1
            quotes_grounded += quote_in_transcript(item.quote, transcript)
        allowed = set(fixture.question.answer_key.required_points) | set(
            fixture.question.answer_key.strong_signals
        )
        for point in evaluation.missing_points:
            points_total += 1
            points_matched += point in allowed

        entry = per_fixture.setdefault(fixture_name, {})
        runs = entry.setdefault(quality, {"overall_by_run": {}, "scores_by_run": {}})
        runs["overall_by_run"][run] = overall_score(evaluation)
        runs["scores_by_run"][run] = {
            dimension: getattr(evaluation.scores, dimension)
            for dimension in SCORE_DIMENSIONS
        }

    for entry in per_fixture.values():
        run0 = {
            quality: data["overall_by_run"].get(0) for quality, data in entry.items()
        }
        if all(run0.get(quality) is not None for quality in ANSWER_QUALITIES):
            entry["ordering_ok"] = run0["bad"] < run0["mediocre"] < run0["strong"]
        # stability spread per dimension (max - min across runs), only
        # meaningful when the stability suite ran (multiple runs cached)
        for data in list(entry.values()):
            if not isinstance(data, dict) or len(data["scores_by_run"]) < 2:
                continue
            data["spread"] = {
                dimension: max(s[dimension] for s in data["scores_by_run"].values())
                - min(s[dimension] for s in data["scores_by_run"].values())
                for dimension in SCORE_DIMENSIONS
            }

    judge_backend = os.environ.get("EVAL_JUDGE", "mock")
    if judge_backend == "anthropic":
        from app.config import settings

        judge_model = settings.anthropic_judge_model
    else:
        judge_model = "mock"

    return {
        "judge_backend": judge_backend,
        "judge_model": judge_model,
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluations": len(_evaluation_cache),
        "grounding": {
            "quotes_total": quotes_total,
            "quotes_grounded": quotes_grounded,
            "rate": quotes_grounded / quotes_total if quotes_total else None,
        },
        "key_adherence": {
            "points_total": points_total,
            "points_matched": points_matched,
            "rate": points_matched / points_total if points_total else None,
        },
        "fixtures": per_fixture,
    }


def pytest_sessionfinish(session, exitstatus):
    if not _evaluation_cache:
        return
    RESULTS_DIR.mkdir(exist_ok=True)
    judge_backend = os.environ.get("EVAL_JUDGE", "mock")
    report_path = RESULTS_DIR / f"{judge_backend}.json"
    report_path.write_text(
        json.dumps(_build_report(), indent=2) + "\n", encoding="utf-8"
    )
