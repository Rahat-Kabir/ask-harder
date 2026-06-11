"""Shared interviewer output rules for mock and DeepSeek backends."""

from collections.abc import Iterator

from app.schemas import InterviewerReply, InterviewQuestion, Turn

DONE_MARKER = "[[DONE]]"


def parse_interviewer_output(text: str, probes_left: int) -> InterviewerReply:
    if probes_left <= 0:
        return InterviewerReply(done=True)

    stripped = text.strip()
    if not stripped or stripped == DONE_MARKER:
        return InterviewerReply(done=True)

    if DONE_MARKER in stripped:
        without_marker = stripped.replace(DONE_MARKER, "").strip()
        if not without_marker:
            return InterviewerReply(done=True)
        return InterviewerReply(text=without_marker)

    return InterviewerReply(text=stripped)


def iter_text_chunks(text: str, chunk_size: int = 32) -> Iterator[str]:
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


def build_interviewer_messages(
    question: InterviewQuestion,
    turns: list[Turn],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "user",
            "content": (
                f"Interview question ({question.qtype.value}):\n{question.text}"
            ),
        }
    ]
    for turn in turns:
        role = "assistant" if turn.role == "interviewer" else "user"
        messages.append({"role": role, "content": turn.content})
    return messages
