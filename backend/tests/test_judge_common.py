from app.llm.judge_common import (
    filter_missing_points,
    quote_in_transcript,
    validate_evidence,
)
from app.schemas import AnswerKey, EvidenceItem, Turn


def test_quote_in_transcript_ignores_case_and_whitespace():
    transcript = "I led the API migration over two quarters."
    assert quote_in_transcript("led the API migration", transcript)


def test_quote_not_in_transcript():
    transcript = "I worked on backend services."
    assert not quote_in_transcript("I invented Kubernetes", transcript)


def test_ellipsis_spliced_quote_grounds_when_all_segments_verbatim():
    transcript = "I built a rate limiter with Redis. Later I added fail-open behavior."
    assert quote_in_transcript(
        "a rate limiter with Redis... fail-open behavior", transcript
    )
    assert quote_in_transcript("a rate limiter… fail-open behavior", transcript)


def test_ellipsis_spliced_quote_fails_when_any_segment_invented():
    transcript = "I built a rate limiter with Redis."
    assert not quote_in_transcript(
        "a rate limiter with Redis... using Kafka", transcript
    )


def test_quote_of_only_ellipsis_is_not_grounded():
    assert not quote_in_transcript("...", "any transcript at all")


def test_validate_evidence_keeps_only_grounded_quotes():
    turns = [
        Turn(role="interviewer", content="Tell me about a project."),
        Turn(role="candidate", content="I built a rate limiter with Redis."),
    ]
    evidence = [
        EvidenceItem(claim="Used Redis", quote="rate limiter with Redis"),
        EvidenceItem(claim="Invented k8s", quote="invented kubernetes"),
    ]
    validated, all_grounded = validate_evidence(turns, evidence)
    assert len(validated) == 1
    assert validated[0].quote == "rate limiter with Redis"
    assert all_grounded is False


def test_filter_missing_points_from_answer_key_only():
    answer_key = AnswerKey(
        required_points=["Names an algorithm", "Stores state"],
        strong_signals=["Discusses failure modes"],
    )
    filtered = filter_missing_points(
        ["Names an algorithm", "Made-up point", "Discusses failure modes"],
        answer_key,
    )
    assert filtered == ["Names an algorithm", "Discusses failure modes"]
