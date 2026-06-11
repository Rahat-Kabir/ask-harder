from app.llm.deepseek_common import deepseek_completion_kwargs


def test_deepseek_thinking_enabled_includes_reasoning_effort():
    kwargs = deepseek_completion_kwargs(thinking="enabled", reasoning_effort="high")
    assert kwargs == {
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": "high",
    }


def test_deepseek_thinking_disabled_omits_reasoning_effort():
    kwargs = deepseek_completion_kwargs(thinking="disabled", reasoning_effort="max")
    assert kwargs == {"extra_body": {"thinking": {"type": "disabled"}}}
