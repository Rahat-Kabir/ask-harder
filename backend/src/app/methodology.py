"""Public eval results — the data behind the /methodology page.

Serves the committed judge-eval artifacts from evals/results/. No auth, no
DB: the page is the public proof that the judge is measured, so it must be
readable without an account.
"""

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

# backend/evals/results — sibling of src/, committed to the repo
RESULTS_DIR = Path(__file__).resolve().parents[2] / "evals" / "results"

router = APIRouter(tags=["methodology"])


class SuiteRate(BaseModel):
    """Counted checks for one suite (grounding quotes or adherence points)."""

    rate: float | None


class GroundingStats(SuiteRate):
    quotes_total: int
    quotes_grounded: int


class KeyAdherenceStats(SuiteRate):
    points_total: int
    points_matched: int


class JudgeResults(BaseModel):
    """One judge's eval run — mirrors the artifact evals/conftest.py writes."""

    judge_backend: str
    judge_model: str
    generated_at: str
    evaluations: int
    grounding: GroundingStats
    key_adherence: KeyAdherenceStats
    # per-fixture scores/ordering/spread; shape documented by the writer
    fixtures: dict


class MethodologyOut(BaseModel):
    results: list[JudgeResults]


@router.get("/methodology", response_model=MethodologyOut)
def get_methodology() -> MethodologyOut:
    results = []
    if RESULTS_DIR.is_dir():
        for artifact in sorted(RESULTS_DIR.glob("*.json")):
            data = json.loads(artifact.read_text(encoding="utf-8"))
            results.append(JudgeResults.model_validate(data))
    # real judges first, mock (harness self-test) last
    results.sort(key=lambda entry: entry.judge_backend == "mock")
    return MethodologyOut(results=results)
