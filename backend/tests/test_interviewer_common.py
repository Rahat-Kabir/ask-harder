from collections.abc import AsyncIterator

import pytest

from app.llm.interviewer_common import (
    DONE_MARKER,
    iter_text_chunks,
    parse_interviewer_output,
    strip_done_marker,
)

pytestmark = pytest.mark.anyio


async def _stream(*deltas: str) -> AsyncIterator[str]:
    for delta in deltas:
        yield delta


async def _collect(deltas: AsyncIterator[str]) -> str:
    return "".join([token async for token in strip_done_marker(deltas)])


def test_parse_done_marker_only():
    reply = parse_interviewer_output(DONE_MARKER, probes_left=2)
    assert reply.done
    assert reply.text is None


def test_parse_probe_text():
    reply = parse_interviewer_output("What trade-offs did you consider?", probes_left=1)
    assert not reply.done
    assert reply.text == "What trade-offs did you consider?"


def test_parse_probe_with_trailing_done_marker():
    reply = parse_interviewer_output(
        "Can you be more specific? [[DONE]]", probes_left=1
    )
    assert not reply.done
    assert reply.text == "Can you be more specific?"


def test_parse_respects_zero_probes_left():
    reply = parse_interviewer_output("Follow-up?", probes_left=0)
    assert reply.done


def test_iter_text_chunks_joins_to_original():
    text = "Walk me through a recent project you are proud of."
    assert "".join(iter_text_chunks(text, chunk_size=16)) == text


async def test_strip_done_marker_intact_in_one_delta():
    assert await _collect(_stream("Thanks! ", DONE_MARKER)) == "Thanks! "


async def test_strip_done_marker_split_across_deltas():
    # the leak found in dogfooding: "[[DO" + "NE]]" passed a per-delta replace
    assert await _collect(_stream("[[DO", "NE]]")) == ""
    assert await _collect(_stream("Good. ", "[[D", "ONE", "]]")) == "Good. "


async def test_strip_done_marker_one_char_per_delta():
    assert await _collect(_stream(*DONE_MARKER)) == ""


async def test_unfinished_marker_prefix_is_real_text():
    # a prefix that never completes must be flushed, not swallowed
    assert await _collect(_stream("see [[", "draft]]")) == "see [[draft]]"
    assert await _collect(_stream("ends with [[DO")) == "ends with [[DO"


async def test_plain_text_passes_through():
    text = "What trade-offs did you consider?"
    assert await _collect(_stream(text[:10], text[10:])) == text
