"""Shared DeepSeek v4 request options (thinking mode, reasoning effort)."""

from typing import Any, Literal

DeepSeekThinking = Literal["enabled", "disabled"]
DeepSeekReasoningEffort = Literal["high", "max"]


def deepseek_completion_kwargs(
    *,
    thinking: DeepSeekThinking,
    reasoning_effort: DeepSeekReasoningEffort,
) -> dict[str, Any]:
    """Build optional kwargs for OpenAI SDK chat.completions.create against DeepSeek."""
    kwargs: dict[str, Any] = {
        "extra_body": {"thinking": {"type": thinking}},
    }
    if thinking == "enabled":
        kwargs["reasoning_effort"] = reasoning_effort
    return kwargs
