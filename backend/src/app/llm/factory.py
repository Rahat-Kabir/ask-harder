from app.config import settings
from app.llm.composite import CompositeLlmBackend
from app.llm.intake import (
    DeepSeekIntakeParser,
    DeepSeekJsonClient,
    DeepSeekPlanGenerator,
)
from app.llm.interviewer import DeepSeekInterviewer
from app.llm.judge import AnthropicJudge
from app.llm.mock import MockBackend


def build_llm_backend() -> MockBackend | CompositeLlmBackend:
    mock = MockBackend()
    if settings.llm_backend == "mock":
        return mock

    if not settings.deepseek_api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is required when LLM_BACKEND=deepseek"
        )
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required when LLM_BACKEND=deepseek"
        )

    intake_client = DeepSeekJsonClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_intake_model,
        max_tokens=settings.deepseek_intake_max_tokens,
    )
    plan_client = DeepSeekJsonClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_plan_model,
        max_tokens=settings.deepseek_plan_max_tokens,
    )
    interviewer = DeepSeekInterviewer(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_interviewer_model,
        max_tokens=settings.deepseek_interviewer_max_tokens,
    )
    judge = AnthropicJudge(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_judge_model,
        max_tokens=settings.anthropic_judge_max_tokens,
    )
    return CompositeLlmBackend(
        intake=DeepSeekIntakeParser(intake_client),
        planner=DeepSeekPlanGenerator(plan_client),
        interviewer=interviewer,
        judge=judge,
    )
