"""Shared interviewer output rules for mock and DeepSeek backends."""

from collections.abc import AsyncIterator, Iterator

from app.schemas import InterviewerReply, InterviewQuestion, Turn

DONE_MARKER = "[[DONE]]"


def _partial_marker_suffix_length(text: str) -> int:
    """Length of the longest suffix of text that could still grow into
    DONE_MARKER as more deltas arrive."""
    longest = min(len(text), len(DONE_MARKER) - 1)
    for length in range(longest, 0, -1):
        if text.endswith(DONE_MARKER[:length]):
            return length
    return 0


async def strip_done_marker(deltas: AsyncIterator[str]) -> AsyncIterator[str]:
    """Remove DONE_MARKER from a token stream, even when the marker arrives
    split across deltas (a per-delta replace cannot catch "[[DO" + "NE]]",
    which is how the sentinel leaked into the chat UI).

    Holds back any trailing text that is a prefix of the marker; emits it
    once it provably cannot complete, or at end of stream (an unfinished
    prefix is real text, not a marker).
    """
    buffer = ""
    async for delta in deltas:
        if not delta:
            continue
        buffer += delta
        buffer = buffer.replace(DONE_MARKER, "")
        held_back = _partial_marker_suffix_length(buffer)
        emit = buffer[: len(buffer) - held_back]
        if emit:
            yield emit
        buffer = buffer[len(buffer) - held_back :]
    if buffer:
        yield buffer


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
