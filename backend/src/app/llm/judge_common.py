"""Post-validation for judge output — evidence must be grounded in the transcript."""

import re

from app.schemas import AnswerKey, EvidenceItem, Turn


def normalize_for_grounding(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.lower()).strip()
    return collapsed


def candidate_transcript(turns: list[Turn]) -> str:
    return " ".join(turn.content for turn in turns if turn.role == "candidate")


def quote_in_transcript(quote: str, transcript: str) -> bool:
    if not quote.strip():
        return False
    normalized_transcript = normalize_for_grounding(transcript)
    # Judges splice non-adjacent passages with "..." despite being told not
    # to (measured in evals). The quote is still honest if every spliced
    # segment is verbatim, so ground each segment independently.
    segments = [segment for segment in re.split(r"\.\.\.|…", quote) if segment.strip()]
    if not segments:
        return False
    return all(
        normalize_for_grounding(segment) in normalized_transcript
        for segment in segments
    )


def validate_evidence(
    turns: list[Turn],
    evidence: list[EvidenceItem],
) -> tuple[list[EvidenceItem], bool]:
    transcript = candidate_transcript(turns)
    validated: list[EvidenceItem] = []
    all_grounded = True
    for item in evidence:
        if quote_in_transcript(item.quote, transcript):
            validated.append(item)
        else:
            all_grounded = False
    return validated, all_grounded


def filter_missing_points(
    missing_points: list[str],
    answer_key: AnswerKey,
) -> list[str]:
    allowed = set(answer_key.required_points) | set(answer_key.strong_signals)
    return [point for point in missing_points if point in allowed]


def build_judge_user_prompt(
    question_text: str, answer_key: AnswerKey, turns: list[Turn]
) -> str:
    transcript_lines = [
        f"{turn.role}: {turn.content}" for turn in turns if turn.content.strip()
    ]
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no turns)"

    return (
        f"Question:\n{question_text}\n\n"
        f"Answer key JSON:\n{answer_key.model_dump_json()}\n\n"
        f"Transcript for this question:\n{transcript}"
    )
