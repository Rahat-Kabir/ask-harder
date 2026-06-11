import json

import pytest

from app.llm.composite import CompositeLlmBackend
from app.llm.errors import IntakeParseError, LlmValidationError
from app.llm.factory import build_llm_backend
from app.llm.intake import (
    DeepSeekIntakeParser,
    DeepSeekJsonClient,
    DeepSeekPlanGenerator,
)
from app.llm.interfaces import IntakeParser, Interviewer, Judge, PlanGenerator
from app.llm.mock import MockBackend
from app.schemas import Profile, QuestionType

pytestmark = pytest.mark.anyio

PROFILE_JSON = {
    "role": "Backend Engineer",
    "seniority": "mid",
    "stack": ["python", "fastapi"],
    "competencies": ["api-design"],
    "resume_claims": [],
}

PLAN_JSON = {
    "questions": [
        {
            "qtype": "warmup",
            "text": "Tell me about a recent project.",
            "tags": ["behavioral/ownership"],
            "answer_key": {
                "required_points": ["Names a project", "Describes their role"],
                "strong_signals": [],
                "red_flags": [],
            },
        },
        {
            "qtype": "technical",
            "text": "How does indexing affect write throughput?",
            "tags": ["databases/indexing"],
            "answer_key": {
                "required_points": ["Indexes speed reads", "Indexes slow writes"],
                "strong_signals": [],
                "red_flags": [],
            },
        },
        {
            "qtype": "technical",
            "text": "Design a rate limiter.",
            "tags": ["system_design/rate-limiting"],
            "answer_key": {
                "required_points": ["Picks an algorithm", "Stores state somewhere"],
                "strong_signals": [],
                "red_flags": [],
            },
        },
    ]
}


class FakeDeepSeekClient(DeepSeekJsonClient):
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self._calls = 0

    async def complete_json(self, *, system_prompt: str, user_prompt: str, schema):
        payload = self._payloads[min(self._calls, len(self._payloads) - 1)]
        self._calls += 1
        if payload.get("error") == "unusable_jd":
            raise LlmValidationError(json.dumps(payload))
        return schema.model_validate(payload)


async def test_deepseek_intake_returns_profile():
    parser = DeepSeekIntakeParser(FakeDeepSeekClient([PROFILE_JSON]))
    profile = await parser.parse("Backend role with Python and FastAPI.")
    assert profile.role == "Backend Engineer"
    assert profile.seniority == "mid"
    assert "python" in profile.stack


async def test_deepseek_intake_raises_on_unusable_jd():
    parser = DeepSeekIntakeParser(FakeDeepSeekClient([{"error": "unusable_jd"}]))
    with pytest.raises(IntakeParseError):
        await parser.parse("asdfgh")


async def test_deepseek_plan_assigns_positions_and_count():
    planner = DeepSeekPlanGenerator(FakeDeepSeekClient([PLAN_JSON]))
    profile = Profile.model_validate(PROFILE_JSON)
    plan = await planner.generate(profile, skill_profile={}, n_questions=3)
    assert len(plan.questions) == 3
    assert [question.position for question in plan.questions] == [0, 1, 2]
    assert plan.questions[1].qtype == QuestionType.technical


async def test_deepseek_plan_rejects_wrong_question_count():
    planner = DeepSeekPlanGenerator(FakeDeepSeekClient([PLAN_JSON]))
    profile = Profile.model_validate(PROFILE_JSON)
    with pytest.raises(LlmValidationError):
        await planner.generate(profile, skill_profile={}, n_questions=2)


def test_composite_backend_implements_all_four_interfaces():
    mock = MockBackend()
    composite = CompositeLlmBackend(
        intake=mock,
        planner=mock,
        interviewer=mock,
        judge=mock,
    )
    assert isinstance(composite, IntakeParser)
    assert isinstance(composite, PlanGenerator)
    assert isinstance(composite, Interviewer)
    assert isinstance(composite, Judge)


def test_factory_defaults_to_mock_backend(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_backend", "mock")
    backend = build_llm_backend()
    assert isinstance(backend, MockBackend)


def test_factory_deepseek_requires_anthropic_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_backend", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_llm_backend()
