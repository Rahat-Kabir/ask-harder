from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.llm.interviewer_common import (
    build_interviewer_messages,
    parse_interviewer_output,
    strip_done_marker,
)
from app.llm.prompts import interviewer_system_prompt
from app.schemas import InterviewerReply, InterviewQuestion, Turn


class DeepSeekInterviewer:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens

    async def respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> InterviewerReply:
        parts: list[str] = []
        async for token in self.stream_respond(question, turns, probes_left):
            parts.append(token)
        return parse_interviewer_output("".join(parts), probes_left)

    async def stream_respond(
        self,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
    ) -> AsyncIterator[str]:
        if probes_left <= 0:
            return

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": interviewer_system_prompt(probes_left),
                },
                *build_interviewer_messages(question, turns),
            ],
            max_tokens=self._max_tokens,
            stream=True,
        )

        async def raw_deltas() -> AsyncIterator[str]:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        # marker-aware filter so the UI never sees [[DONE]], even split
        # across deltas
        async for token in strip_done_marker(raw_deltas()):
            yield token
