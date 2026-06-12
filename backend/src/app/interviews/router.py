import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth.deps import CurrentUser, DbSession
from app.db.models import InterviewStatus
from app.interviews.events import StreamEventName, StreamMessage
from app.interviews.schemas import (
    AnswerIn,
    CreateInterviewIn,
    CreateInterviewOut,
    InterviewListOut,
    InterviewStateOut,
    QuotaOut,
    ReportOut,
)
from app.interviews.service import (
    InterviewNotFound,
    InterviewService,
    QuotaExceeded,
)
from app.interviews.sse import format_keepalive, format_sse
from app.interviews.state_machine import InvalidTransition

KEEPALIVE_SECONDS = 15.0
# 0 = never auto-close on idle (production). Tests monkeypatch a small value.
MAX_IDLE_POLLS = 0

router = APIRouter(tags=["interviews"])
_service = InterviewService()


@router.post(
    "/interviews",
    response_model=CreateInterviewOut,
    responses={
        201: {"description": "Interview ready (mock backend)"},
        202: {"description": "Interview preparing (DeepSeek intake + plan)"},
    },
)
async def create_interview(
    body: CreateInterviewIn,
    db: DbSession,
    user: CurrentUser,
) -> CreateInterviewOut | JSONResponse:
    try:
        created = await _service.create(
            db,
            user,
            jd_text=body.jd_text,
            resume_text=body.resume_text,
            session_type=body.session_type,
            practice_tag=body.practice_tag,
        )
    except QuotaExceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Daily interview limit reached — resets at midnight UTC",
        ) from None
    status_code = (
        status.HTTP_202_ACCEPTED
        if created.status == "preparing"
        else status.HTTP_201_CREATED
    )
    return JSONResponse(
        status_code=status_code,
        content=created.model_dump(mode="json"),
    )


@router.post(
    "/interviews/{interview_id}/retake",
    response_model=CreateInterviewOut,
    responses={
        201: {"description": "Interview ready (mock backend)"},
        202: {"description": "Interview preparing (DeepSeek intake + plan)"},
    },
)
async def retake_interview(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> CreateInterviewOut | JSONResponse:
    try:
        created = await _service.retake(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except QuotaExceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Daily interview limit reached — resets at midnight UTC",
        ) from None
    status_code = (
        status.HTTP_202_ACCEPTED
        if created.status == "preparing"
        else status.HTTP_201_CREATED
    )
    return JSONResponse(
        status_code=status_code,
        content=created.model_dump(mode="json"),
    )


@router.get("/quota", response_model=QuotaOut)
async def get_quota(db: DbSession, user: CurrentUser) -> QuotaOut:
    return await _service.get_quota(db, user)


@router.get("/interviews", response_model=InterviewListOut)
async def list_interviews(db: DbSession, user: CurrentUser) -> InterviewListOut:
    return await _service.list_interviews(db, user)


@router.get("/interviews/{interview_id}", response_model=InterviewStateOut)
async def get_interview(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> InterviewStateOut:
    try:
        return await _service.get_state(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> None:
    try:
        await _service.delete_interview(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None


@router.post("/interviews/{interview_id}/start", response_model=InterviewStateOut)
async def start_interview(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> InterviewStateOut:
    try:
        return await _service.start(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.detail) from error


@router.post("/interviews/{interview_id}/answer", response_model=InterviewStateOut)
async def submit_answer(
    interview_id: UUID,
    body: AnswerIn,
    db: DbSession,
    user: CurrentUser,
) -> InterviewStateOut:
    try:
        return await _service.submit_answer(db, interview_id, user, body.text)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.detail) from error


@router.post("/interviews/{interview_id}/skip", response_model=InterviewStateOut)
async def skip_question(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> InterviewStateOut:
    try:
        return await _service.skip_question(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.detail) from error


@router.post("/interviews/{interview_id}/finish", response_model=InterviewStateOut)
async def finish_interview(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> InterviewStateOut:
    try:
        return await _service.finish(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.detail) from error


@router.get("/interviews/{interview_id}/stream")
async def stream_interview(
    interview_id: UUID,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> StreamingResponse:
    try:
        interview = await _service.assert_streamable(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.detail) from error

    async def event_generator() -> AsyncIterator[str]:
        if interview.status == InterviewStatus.complete:
            yield format_sse(
                StreamMessage(
                    event=StreamEventName.interview_complete,
                    data={"interview_id": str(interview.id)},
                )
            )
            return

        queue = _service.events.subscribe(interview_id)
        idle_polls = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=KEEPALIVE_SECONDS
                    )
                except TimeoutError:
                    idle_polls += 1
                    if MAX_IDLE_POLLS and idle_polls >= MAX_IDLE_POLLS:
                        break
                    yield format_keepalive()
                    continue
                idle_polls = 0
                if message is None:
                    break
                yield format_sse(message)
                if message.event == StreamEventName.interview_complete:
                    break
        finally:
            _service.events.unsubscribe(interview_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/interviews/{interview_id}/report", response_model=ReportOut)
async def get_report(
    interview_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> ReportOut:
    try:
        return await _service.get_report(db, interview_id, user)
    except InterviewNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found") from None
    except InvalidTransition as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.detail) from error
