"""Interview flow rules — the backend owns all transitions."""

from app.db.models import Interview, InterviewStatus, InterviewTurn, TurnRole

MAX_PROBES_PER_QUESTION = 2


class InvalidTransition(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def question_count(dev_mode: bool) -> int:
    return 3 if dev_mode else 7


def assert_status(
    interview: Interview,
    allowed: InterviewStatus | set[InterviewStatus],
) -> None:
    if isinstance(allowed, InterviewStatus):
        allowed = {allowed}
    if interview.status not in allowed:
        raise InvalidTransition(
            f"Interview is {interview.status.value}; expected "
            f"{', '.join(s.value for s in allowed)}"
        )


def probes_used_on_question(turns: list[InterviewTurn]) -> int:
    return sum(
        1 for turn in turns if turn.role == TurnRole.interviewer and turn.is_probe
    )


def awaiting_answer(turns: list[InterviewTurn]) -> bool:
    """True when the last turn is from the interviewer (question or probe)."""
    return bool(turns) and turns[-1].role == TurnRole.interviewer


def all_questions_answered(
    interview: Interview,
    question_count_total: int,
    current_question_turns: list[InterviewTurn],
) -> bool:
    if interview.current_question_position != question_count_total - 1:
        return False
    if not current_question_turns:
        return False
    return current_question_turns[-1].role == TurnRole.candidate
