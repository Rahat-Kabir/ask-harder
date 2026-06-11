import pytest

from app.llm.judge import AnthropicJudge
from app.llm.errors import LlmEmptyResponse
from app.schemas import (
    AnswerKey,
    Evaluation,
    EvidenceItem,
    PlannedQuestion,
    QuestionType,
    Scores,
    Turn,
)

pytestmark = pytest.mark.anyio

QUESTION = PlannedQuestion(
    position=0,
    qtype=QuestionType.technical,
    text="How would you design a rate limiter?",
    tags=["system_design/rate-limiting"],
    answer_key=AnswerKey(
        required_points=["Picks an algorithm", "Stores state somewhere"],
        strong_signals=["Discusses distributed concerns"],
    ),
)

TURNS = [
    Turn(role="interviewer", content="How would you design a rate limiter?"),
    Turn(
        role="candidate",
        content="I would use a token bucket in Redis keyed by client id.",
    ),
]

GOOD_EVALUATION = Evaluation(
    scores=Scores(correctness=3, depth=3, structure=3, communication=3),
    evidence=[
        EvidenceItem(
            claim="Names token bucket",
            quote="token bucket in Redis keyed by client id",
        )
    ],
    missing_points=["Discusses distributed concerns"],
    model_answer="Token bucket or sliding window with shared Redis state.",
)

BAD_GROUNDING_EVALUATION = Evaluation(
    scores=Scores(correctness=2, depth=2, structure=2, communication=2),
    evidence=[
        EvidenceItem(claim="Hallucinated", quote="I used Kafka for rate limits")
    ],
    missing_points=["Picks an algorithm"],
    model_answer="Explain algorithm and storage.",
)

FIXED_EVALUATION = Evaluation(
    scores=Scores(correctness=3, depth=2, structure=3, communication=3),
    evidence=[
        EvidenceItem(
            claim="Mentions Redis",
            quote="token bucket in Redis keyed by client id",
        )
    ],
    missing_points=["Picks an algorithm"],
    model_answer="Token bucket with Redis.",
)


class _FakeParsedResponse:
    def __init__(self, evaluation: Evaluation | None) -> None:
        self.parsed_output = evaluation


class _FakeMessages:
    def __init__(self, evaluations: list[Evaluation | None]) -> None:
        self._evaluations = evaluations
        self._calls = 0
        self.last_kwargs: dict | None = None

    async def parse(self, **kwargs):
        self.last_kwargs = kwargs
        payload = self._evaluations[min(self._calls, len(self._evaluations) - 1)]
        self._calls += 1
        return _FakeParsedResponse(payload)


class _FakeAnthropicClient:
    def __init__(self, evaluations: list[Evaluation | None]) -> None:
        self.messages = _FakeMessages(evaluations)


async def test_anthropic_judge_returns_grounded_evaluation():
    client = _FakeAnthropicClient([GOOD_EVALUATION])
    judge = AnthropicJudge(
        api_key="test-key",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        client=client,  # type: ignore[arg-type]
    )

    evaluation = await judge.evaluate(QUESTION, TURNS)

    assert evaluation.scores.correctness == 3
    assert len(evaluation.evidence) == 1
    assert evaluation.missing_points == ["Discusses distributed concerns"]
    assert client.messages.last_kwargs is not None
    assert client.messages.last_kwargs["model"] == "claude-sonnet-4-6"
    assert client.messages.last_kwargs["thinking"] == {"type": "adaptive"}


async def test_anthropic_judge_retries_on_bad_grounding():
    client = _FakeAnthropicClient([BAD_GROUNDING_EVALUATION, FIXED_EVALUATION])
    judge = AnthropicJudge(
        api_key="test-key",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        client=client,  # type: ignore[arg-type]
    )

    evaluation = await judge.evaluate(QUESTION, TURNS)

    assert client.messages._calls == 2
    assert len(evaluation.evidence) == 1
    assert "token bucket" in evaluation.evidence[0].quote


async def test_anthropic_judge_strips_invalid_evidence_after_retry():
    client = _FakeAnthropicClient(
        [BAD_GROUNDING_EVALUATION, BAD_GROUNDING_EVALUATION]
    )
    judge = AnthropicJudge(
        api_key="test-key",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        client=client,  # type: ignore[arg-type]
    )

    evaluation = await judge.evaluate(QUESTION, TURNS)

    assert client.messages._calls == 2
    assert evaluation.evidence == []


async def test_anthropic_judge_raises_on_empty_parse():
    client = _FakeAnthropicClient([None])
    judge = AnthropicJudge(
        api_key="test-key",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        client=client,  # type: ignore[arg-type]
    )

    with pytest.raises(LlmEmptyResponse):
        await judge.evaluate(QUESTION, TURNS)
