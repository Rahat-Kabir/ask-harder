import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    Interview,
    InterviewStatus,
    InterviewTurn,
    Question,
    QuestionEvaluation,
    SessionType,
    TurnRole,
    User,
)
from app.db.session import new_session
from app.interviews.events import InterviewEventBus, StreamEventName, interview_events
from app.interviews.schemas import (
    CreateInterviewOut,
    EvaluationOut,
    InterviewListOut,
    InterviewStateOut,
    InterviewSummaryOut,
    ReportOut,
    ReportQuestionOut,
    TurnOut,
)
from app.interviews.state_machine import (
    MAX_PROBES_PER_QUESTION,
    InvalidTransition,
    all_questions_answered,
    assert_status,
    awaiting_answer,
    probes_used_on_question,
    question_count,
)
from app.llm.composite import CompositeLlmBackend
from app.llm.errors import LlmError
from app.llm.factory import build_llm_backend
from app.llm.interviewer_common import iter_text_chunks, parse_interviewer_output
from app.llm.mock import MockBackend
from app.schemas import (
    AnswerKey,
    EvidenceItem,
    InterviewerReply,
    InterviewQuestion,
    PlannedQuestion,
    Profile,
    Scores,
    Turn,
)
from app.skills.service import (
    load_skill_profile,
    overall_score,
    record_skill_scores,
    skill_average,
)

logger = logging.getLogger(__name__)
LlmBackend = MockBackend | CompositeLlmBackend

# strong references to fire-and-forget preparation tasks (see create())
_background_tasks: set[asyncio.Task] = set()

# newest interviews returned by the history list — no pagination yet
HISTORY_LIMIT = 50


class InterviewService:
    def __init__(
        self,
        llm: LlmBackend | None = None,
        events: InterviewEventBus | None = None,
    ) -> None:
        self.llm = llm or build_llm_backend()
        self.events = events or interview_events

    async def create(
        self,
        db: AsyncSession,
        user: User,
        jd_text: str | None,
        resume_text: str | None,
        session_type: SessionType,
        practice_tag: str | None = None,
    ) -> CreateInterviewOut:
        interview = Interview(
            user_id=user.id,
            status=InterviewStatus.preparing,
            jd_text=jd_text or "",
            resume_text=resume_text,
            session_type=session_type,
            practice_tag=practice_tag,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)

        if settings.llm_backend == "mock":
            await self._prepare_interview(db, interview.id)
            return CreateInterviewOut(id=interview.id, status="ready")

        task = asyncio.create_task(self._prepare_interview_background(interview.id))
        # the event loop holds tasks weakly — without a reference the task
        # can be garbage-collected mid-run
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return CreateInterviewOut(id=interview.id, status="preparing")

    async def _prepare_interview_background(self, interview_id: uuid.UUID) -> None:
        try:
            async with new_session() as db:
                await self._prepare_interview(db, interview_id)
        except Exception:
            logger.exception(
                "Background interview preparation failed for %s", interview_id
            )

    async def _prepare_interview(
        self, db: AsyncSession, interview_id: uuid.UUID
    ) -> None:
        interview = await db.get(Interview, interview_id)
        if interview is None or interview.status != InterviewStatus.preparing:
            return

        try:
            if interview.practice_tag is not None:
                # skill drill: no JD, no intake parse — plan straight
                # from the tag and the user's current average on it
                profile = None
                average = await skill_average(
                    db, interview.user_id, interview.practice_tag
                )
                plan = await self.llm.generate_practice(
                    interview.practice_tag,
                    average,
                    n_questions=question_count(interview.session_type),
                )
            else:
                profile = await self.llm.parse(interview.jd_text, interview.resume_text)
                skill_profile = await load_skill_profile(db, interview.user_id)
                plan = await self.llm.generate(
                    profile,
                    skill_profile=skill_profile,
                    n_questions=question_count(interview.session_type),
                )
        except LlmError:
            # covers IntakeParseError too — any provider failure during
            # preparation abandons the interview
            interview.status = InterviewStatus.abandoned
            await db.commit()
            return

        if profile is not None:
            interview.profile_json = profile.model_dump()
        for planned in plan.questions:
            db.add(
                Question(
                    interview_id=interview.id,
                    position=planned.position,
                    qtype=planned.qtype,
                    text=planned.text,
                    answer_key_json=planned.answer_key.model_dump(),
                    tags=planned.tags,
                )
            )

        interview.status = InterviewStatus.ready
        await db.commit()

    async def get_state(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
    ) -> InterviewStateOut:
        interview = await self._load_owned_interview(db, interview_id, user)
        return await self._build_state(db, interview)

    async def start(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
    ) -> InterviewStateOut:
        interview = await self._load_owned_interview(db, interview_id, user)
        assert_status(interview, InterviewStatus.ready)

        questions = await self._load_questions(db, interview.id)
        first_question = questions[0]

        interview.status = InterviewStatus.in_progress
        interview.current_question_position = 0
        db.add(
            await self._new_turn(
                db,
                interview_id=interview.id,
                question_id=first_question.id,
                role=TurnRole.interviewer,
                content=first_question.text,
            )
        )
        await db.commit()
        await db.refresh(interview)
        await self._emit_interviewer_presentation(
            interview.id,
            position=first_question.position,
            qtype=first_question.qtype.value,
            text=first_question.text,
            is_probe=False,
            is_new_question=True,
        )
        return await self._build_state(db, interview)

    async def submit_answer(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
        text: str,
    ) -> InterviewStateOut:
        interview = await self._load_owned_interview(db, interview_id, user)
        assert_status(interview, InterviewStatus.in_progress)

        if interview.current_question_position is None:
            raise InvalidTransition("Interview has not been started")

        questions = await self._load_questions(db, interview.id)
        current_question = questions[interview.current_question_position]
        turns = await self._load_turns_for_question(db, current_question.id)

        if not awaiting_answer(turns):
            raise InvalidTransition("Not awaiting an answer on the current question")

        db.add(
            await self._new_turn(
                db,
                interview_id=interview.id,
                question_id=current_question.id,
                role=TurnRole.candidate,
                content=text,
            )
        )
        await db.flush()
        turns = await self._load_turns_for_question(db, current_question.id)

        probes_left = MAX_PROBES_PER_QUESTION - probes_used_on_question(turns)
        llm_turns = self._to_llm_turns(turns)
        public_question = InterviewQuestion(
            position=current_question.position,
            qtype=current_question.qtype,
            text=current_question.text,
        )
        reply = await self._stream_interviewer_reply(
            interview.id,
            public_question,
            llm_turns,
            probes_left,
            position=current_question.position,
            qtype=current_question.qtype.value,
            is_probe=True,
            is_new_question=False,
        )

        if not reply.done and reply.text and probes_left > 0:
            db.add(
                await self._new_turn(
                    db,
                    interview_id=interview.id,
                    question_id=current_question.id,
                    role=TurnRole.interviewer,
                    content=reply.text,
                    is_probe=True,
                )
            )
            await db.commit()
            return await self._build_state(db, interview)

        if interview.current_question_position < len(questions) - 1:
            interview.current_question_position += 1
            next_question = questions[interview.current_question_position]
            db.add(
                await self._new_turn(
                    db,
                    interview_id=interview.id,
                    question_id=next_question.id,
                    role=TurnRole.interviewer,
                    content=next_question.text,
                )
            )
            await db.commit()
            await self._emit_interviewer_presentation(
                interview.id,
                position=next_question.position,
                qtype=next_question.qtype.value,
                text=next_question.text,
                is_probe=False,
                is_new_question=True,
            )
            return await self._build_state(db, interview)

        await db.commit()
        return await self._build_state(db, interview)

    async def finish(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
    ) -> InterviewStateOut:
        interview = await self._load_owned_interview(db, interview_id, user)
        assert_status(interview, InterviewStatus.in_progress)

        questions = await self._load_questions(db, interview.id)
        current_question = questions[interview.current_question_position or 0]
        current_turns = await self._load_turns_for_question(db, current_question.id)

        if not all_questions_answered(interview, len(questions), current_turns):
            raise InvalidTransition("Not all questions have been answered yet")

        interview.status = InterviewStatus.judging
        await db.flush()

        for question in questions:
            turns = await self._load_turns_for_question(db, question.id)
            planned = self._to_planned_question(question)
            evaluation = await self.llm.evaluate(planned, self._to_llm_turns(turns))
            db.add(
                QuestionEvaluation(
                    interview_id=interview.id,
                    question_id=question.id,
                    scores_json=evaluation.scores.model_dump(),
                    evidence_json=[item.model_dump() for item in evaluation.evidence],
                    missing_points_json=evaluation.missing_points,
                    model_answer=evaluation.model_answer,
                    judge_model=self._judge_model_name(),
                )
            )
            await record_skill_scores(
                db,
                user_id=user.id,
                tags=list(question.tags),
                scores=evaluation.scores,
            )

        interview.status = InterviewStatus.complete
        interview.finished_at = datetime.now(UTC)
        await db.commit()
        self.events.publish(
            interview.id,
            StreamEventName.interview_complete,
            {"interview_id": str(interview.id)},
        )
        self.events.close(interview.id)
        return await self._build_state(db, interview)

    async def get_report(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
    ) -> ReportOut:
        interview = await self._load_owned_interview(db, interview_id, user)
        if interview.status != InterviewStatus.complete:
            raise InvalidTransition("Report is not ready yet")

        # practice drills have no profile; JD interviews must have one
        if interview.finished_at is None or (
            interview.profile_json is None and interview.practice_tag is None
        ):
            raise InvalidTransition("Interview data is incomplete")

        profile = (
            Profile.model_validate(interview.profile_json)
            if interview.profile_json is not None
            else None
        )
        questions = await self._load_questions(db, interview.id)
        all_turns = await self._load_all_turns(db, interview.id)
        evaluations = await self._load_evaluations(db, interview.id)
        eval_by_question = {
            evaluation.question_id: evaluation for evaluation in evaluations
        }

        report_questions: list[ReportQuestionOut] = []
        for question in questions:
            question_turns = [
                turn for turn in all_turns if turn.question_id == question.id
            ]
            stored_eval = eval_by_question[question.id]
            report_questions.append(
                ReportQuestionOut(
                    position=question.position,
                    qtype=question.qtype,
                    text=question.text,
                    tags=list(question.tags),
                    answer_key=AnswerKey.model_validate(question.answer_key_json),
                    turns=[
                        self._turn_out(turn, question.position)
                        for turn in question_turns
                    ],
                    evaluation=EvaluationOut(
                        scores=Scores.model_validate(stored_eval.scores_json),
                        evidence=[
                            EvidenceItem.model_validate(item)
                            for item in stored_eval.evidence_json
                        ],
                        missing_points=list(stored_eval.missing_points_json),
                        model_answer=stored_eval.model_answer,
                        judge_model=stored_eval.judge_model,
                    ),
                )
            )

        return ReportOut(
            id=interview.id,
            status="complete",
            profile=profile,
            practice_tag=interview.practice_tag,
            session_type=interview.session_type,
            finished_at=interview.finished_at,
            questions=report_questions,
        )

    async def list_interviews(self, db: AsyncSession, user: User) -> InterviewListOut:
        interviews = (
            (
                await db.execute(
                    select(Interview)
                    .where(Interview.user_id == user.id)
                    .order_by(Interview.created_at.desc())
                    .limit(HISTORY_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        interview_ids = [interview.id for interview in interviews]

        question_counts: dict[uuid.UUID, int] = {}
        scores_by_interview: dict[uuid.UUID, list[float]] = {}
        if interview_ids:
            count_rows = await db.execute(
                select(Question.interview_id, func.count())
                .where(Question.interview_id.in_(interview_ids))
                .group_by(Question.interview_id)
            )
            question_counts = dict(count_rows.all())

            evaluation_rows = await db.execute(
                select(
                    QuestionEvaluation.interview_id, QuestionEvaluation.scores_json
                ).where(QuestionEvaluation.interview_id.in_(interview_ids))
            )
            for interview_id, scores_json in evaluation_rows.all():
                scores_by_interview.setdefault(interview_id, []).append(
                    overall_score(Scores.model_validate(scores_json))
                )

        summaries: list[InterviewSummaryOut] = []
        for interview in interviews:
            profile = (
                Profile.model_validate(interview.profile_json)
                if interview.profile_json is not None
                else None
            )
            question_scores = scores_by_interview.get(interview.id)
            summaries.append(
                InterviewSummaryOut(
                    id=interview.id,
                    status=interview.status.value,
                    session_type=interview.session_type,
                    practice_tag=interview.practice_tag,
                    role=profile.role if profile else None,
                    seniority=profile.seniority if profile else None,
                    question_count=question_counts.get(interview.id, 0),
                    overall_score=(
                        sum(question_scores) / len(question_scores)
                        if question_scores
                        else None
                    ),
                    created_at=interview.created_at,
                    finished_at=interview.finished_at,
                )
            )
        return InterviewListOut(interviews=summaries)

    async def _load_owned_interview(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
    ) -> Interview:
        result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.user_id == user.id,
            )
        )
        interview = result.scalar_one_or_none()
        if interview is None:
            raise InterviewNotFound()
        return interview

    async def _load_questions(
        self, db: AsyncSession, interview_id: uuid.UUID
    ) -> list[Question]:
        result = await db.execute(
            select(Question)
            .where(Question.interview_id == interview_id)
            .order_by(Question.position)
        )
        return list(result.scalars().all())

    async def _load_turns_for_question(
        self, db: AsyncSession, question_id: uuid.UUID
    ) -> list[InterviewTurn]:
        result = await db.execute(
            select(InterviewTurn)
            .where(InterviewTurn.question_id == question_id)
            .order_by(InterviewTurn.sequence)
        )
        return list(result.scalars().all())

    async def _load_all_turns(
        self, db: AsyncSession, interview_id: uuid.UUID
    ) -> list[InterviewTurn]:
        result = await db.execute(
            select(InterviewTurn)
            .where(InterviewTurn.interview_id == interview_id)
            .order_by(InterviewTurn.sequence)
        )
        return list(result.scalars().all())

    async def _load_evaluations(
        self, db: AsyncSession, interview_id: uuid.UUID
    ) -> list[QuestionEvaluation]:
        result = await db.execute(
            select(QuestionEvaluation).where(
                QuestionEvaluation.interview_id == interview_id
            )
        )
        return list(result.scalars().all())

    async def _build_state(
        self, db: AsyncSession, interview: Interview
    ) -> InterviewStateOut:
        questions = await self._load_questions(db, interview.id)
        all_turns = await self._load_all_turns(db, interview.id)
        question_by_id = {question.id: question for question in questions}

        current_question: InterviewQuestion | None = None
        current_turns: list[InterviewTurn] = []
        if interview.current_question_position is not None and questions:
            current_db_question = questions[interview.current_question_position]
            current_question = InterviewQuestion(
                position=current_db_question.position,
                qtype=current_db_question.qtype,
                text=current_db_question.text,
            )
            current_turns = [
                turn for turn in all_turns if turn.question_id == current_db_question.id
            ]

        turn_outs = [
            self._turn_out(turn, question_by_id[turn.question_id].position)
            for turn in all_turns
        ]

        is_awaiting = (
            interview.status == InterviewStatus.in_progress
            and awaiting_answer(current_turns)
        )

        return InterviewStateOut(
            id=interview.id,
            status=interview.status.value,
            session_type=interview.session_type,
            practice_tag=interview.practice_tag,
            question_count=len(questions),
            current_question_position=interview.current_question_position,
            awaiting_answer=is_awaiting,
            current_question=current_question,
            turns=turn_outs,
        )

    async def _new_turn(
        self,
        db: AsyncSession,
        *,
        interview_id: uuid.UUID,
        question_id: uuid.UUID,
        role: TurnRole,
        content: str,
        is_probe: bool = False,
    ) -> InterviewTurn:
        turn_count = (
            await db.execute(
                select(func.count())
                .select_from(InterviewTurn)
                .where(InterviewTurn.interview_id == interview_id)
            )
        ).scalar_one()
        return InterviewTurn(
            interview_id=interview_id,
            question_id=question_id,
            sequence=turn_count,
            role=role,
            content=content,
            is_probe=is_probe,
        )

    @staticmethod
    def _turn_out(turn: InterviewTurn, question_position: int) -> TurnOut:
        return TurnOut(
            id=turn.id,
            role=turn.role.value,
            content=turn.content,
            is_probe=turn.is_probe,
            question_position=question_position,
            created_at=turn.created_at,
        )

    @staticmethod
    def _to_llm_turns(turns: list[InterviewTurn]) -> list[Turn]:
        return [
            Turn(role=turn.role.value, content=turn.content)  # type: ignore[arg-type]
            for turn in turns
        ]

    def _judge_model_name(self) -> str:
        return self.llm.judge_model_name

    async def _stream_interviewer_reply(
        self,
        interview_id: uuid.UUID,
        question: InterviewQuestion,
        turns: list[Turn],
        probes_left: int,
        *,
        position: int,
        qtype: str,
        is_probe: bool,
        is_new_question: bool,
    ) -> InterviewerReply:
        if is_new_question:
            self.events.publish(
                interview_id,
                StreamEventName.question,
                {
                    "position": position,
                    "qtype": qtype,
                    "is_probe": False,
                },
            )

        if probes_left <= 0:
            self.events.publish(
                interview_id,
                StreamEventName.interviewer_done,
                {"question_position": position, "is_probe": is_probe},
            )
            return InterviewerReply(done=True)

        parts: list[str] = []
        async for token in self.llm.stream_respond(question, turns, probes_left):
            parts.append(token)
            self.events.publish(interview_id, StreamEventName.token, {"text": token})

        reply = parse_interviewer_output("".join(parts), probes_left)
        self.events.publish(
            interview_id,
            StreamEventName.interviewer_done,
            {"question_position": position, "is_probe": is_probe},
        )
        return reply

    async def _emit_interviewer_presentation(
        self,
        interview_id: uuid.UUID,
        *,
        position: int,
        qtype: str,
        text: str,
        is_probe: bool,
        is_new_question: bool,
    ) -> None:
        if is_new_question:
            self.events.publish(
                interview_id,
                StreamEventName.question,
                {
                    "position": position,
                    "qtype": qtype,
                    "is_probe": False,
                },
            )
        for chunk in iter_text_chunks(text):
            self.events.publish(interview_id, StreamEventName.token, {"text": chunk})
        self.events.publish(
            interview_id,
            StreamEventName.interviewer_done,
            {"question_position": position, "is_probe": is_probe},
        )

    async def assert_streamable(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        user: User,
    ) -> Interview:
        interview = await self._load_owned_interview(db, interview_id, user)
        if interview.status not in (
            InterviewStatus.ready,
            InterviewStatus.in_progress,
            InterviewStatus.complete,
        ):
            raise InvalidTransition(
                f"Cannot stream interview in status {interview.status.value}"
            )
        return interview

    @staticmethod
    def _to_planned_question(question: Question) -> PlannedQuestion:
        return PlannedQuestion(
            position=question.position,
            qtype=question.qtype,
            text=question.text,
            tags=list(question.tags),
            answer_key=AnswerKey.model_validate(question.answer_key_json),
        )


class InterviewNotFound(Exception):
    pass
