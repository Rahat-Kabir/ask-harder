from app.llm.interviewer_common import (
    DONE_MARKER,
    iter_text_chunks,
    parse_interviewer_output,
)


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
