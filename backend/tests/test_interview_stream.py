import asyncio
import uuid

import pytest

from app.interviews.events import StreamEventName, interview_events

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "stream@example.com", "password": "correct-horse-9"}
OTHER_CREDENTIALS = {"email": "stream-other@example.com", "password": "another-pass-1"}
JD = "Backend Engineer: Python, FastAPI, Postgres."

LONG_ANSWER = (
    "I designed a rate-limited API gateway with token buckets backed by Redis "
    "and measured p99 latency after adding covering indexes on the hot path."
)


async def _register(client, credentials: dict[str, str] = CREDENTIALS) -> None:
    response = await client.post("/api/auth/register", json=credentials)
    assert response.status_code == 201


async def _create_interview(client) -> str:
    response = await client.post(
        "/api/interviews",
        json={"jd_text": JD, "dev_mode": True},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _collect_bus_events(
    interview_id: str, count: int, *, timeout: float = 2.0
) -> list:
    interview_uuid = uuid.UUID(interview_id)
    queue = interview_events.subscribe(interview_uuid)
    events = []
    try:
        for _ in range(count):
            events.append(await asyncio.wait_for(queue.get(), timeout=timeout))
    finally:
        interview_events.unsubscribe(interview_uuid, queue)
    return events


async def test_stream_requires_auth(client):
    interview_id = "00000000-0000-0000-0000-000000000001"
    response = await client.get(f"/api/interviews/{interview_id}/stream")
    assert response.status_code == 401


async def test_stream_404_for_other_user(client):
    await _register(client)
    interview_id = await _create_interview(client)

    await client.post("/api/auth/logout")
    await _register(client, OTHER_CREDENTIALS)

    response = await client.get(f"/api/interviews/{interview_id}/stream")
    assert response.status_code == 404


async def _collect_until_interviewer_done(queue) -> list:
    events = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=2.0)
        events.append(event)
        if event.event == StreamEventName.interviewer_done:
            break
    return events


async def test_start_emits_question_token_interviewer_done(client):
    await _register(client)
    interview_id = await _create_interview(client)
    interview_uuid = uuid.UUID(interview_id)
    queue = interview_events.subscribe(interview_uuid)
    try:
        start = await client.post(f"/api/interviews/{interview_id}/start")
        assert start.status_code == 200
        events = await _collect_until_interviewer_done(queue)
    finally:
        interview_events.unsubscribe(interview_uuid, queue)

    assert events[0].event == StreamEventName.question
    assert all(event.event == StreamEventName.token for event in events[1:-1])
    assert events[-1].event == StreamEventName.interviewer_done
    assert events[0].data["position"] == 0
    assert events[0].data["is_probe"] is False
    streamed_text = "".join(event.data["text"] for event in events[1:-1])
    assert streamed_text
    assert events[-1].data["question_position"] == 0
    assert events[-1].data["is_probe"] is False


async def test_answer_probe_emits_token_without_question_event(client):
    await _register(client)
    interview_id = await _create_interview(client)
    await client.post(f"/api/interviews/{interview_id}/start")

    interview_uuid = uuid.UUID(interview_id)
    queue = interview_events.subscribe(interview_uuid)
    try:
        answer = await client.post(
            f"/api/interviews/{interview_id}/answer",
            json={"text": "I built something once."},
        )
        assert answer.status_code == 200
        events = await _collect_until_interviewer_done(queue)
    finally:
        interview_events.unsubscribe(interview_uuid, queue)

    assert all(event.event == StreamEventName.token for event in events[:-1])
    assert events[-1].event == StreamEventName.interviewer_done
    assert "".join(event.data["text"] for event in events[:-1])
    assert events[-1].data["is_probe"] is True


async def test_finish_emits_interview_complete(client):
    await _register(client)
    interview_id = await _create_interview(client)
    await client.post(f"/api/interviews/{interview_id}/start")

    for _ in range(3):
        await client.post(
            f"/api/interviews/{interview_id}/answer",
            json={"text": "Short answer."},
        )
        await client.post(
            f"/api/interviews/{interview_id}/answer",
            json={"text": LONG_ANSWER},
        )

    interview_uuid = uuid.UUID(interview_id)
    queue = interview_events.subscribe(interview_uuid)
    try:
        finish = await client.post(f"/api/interviews/{interview_id}/finish")
        assert finish.status_code == 200
        event = await asyncio.wait_for(queue.get(), timeout=2.0)
    finally:
        interview_events.unsubscribe(interview_uuid, queue)

    assert event.event == StreamEventName.interview_complete
    assert event.data["interview_id"] == interview_id


async def test_complete_interview_stream_replays_complete_event(client):
    await _register(client)
    interview_id = await _create_interview(client)
    await client.post(f"/api/interviews/{interview_id}/start")

    for _ in range(3):
        await client.post(
            f"/api/interviews/{interview_id}/answer",
            json={"text": "Short answer."},
        )
        await client.post(
            f"/api/interviews/{interview_id}/answer",
            json={"text": LONG_ANSWER},
        )
    await client.post(f"/api/interviews/{interview_id}/finish")

    response = await client.get(f"/api/interviews/{interview_id}/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: interview_complete" in response.text
    assert interview_id in response.text
