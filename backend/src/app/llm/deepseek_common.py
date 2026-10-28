"""Shared DeepSeek v4 request options (thinking mode, reasoning effort)."""

from typing import Any, Literal

DeepSeekThinking = Literal["enabled", "disabled"]
DeepSeekReasoningEffort = Literal["high", "max"]

# HTTP timeout for every DeepSeek client. The OpenAI SDK default is 600s
# (and it retries twice), so a hung connection could hold an interview in
# `preparing`, or an /answer request open, for up to half an hour. httpx
# applies this to each phase separately — for reads it is the longest
# SILENCE allowed between bytes, not a cap on total duration — so a slow
# thinking-mode generation that keeps streaming is unaffected.
DEEPSEEK_TIMEOUT_SECONDS = 120.0


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
