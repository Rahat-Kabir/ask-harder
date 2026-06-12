import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import Interview, Question, QuestionEvaluation, User
from app.db.session import new_session

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "interview@example.com", "password": "correct-horse-9"}
OTHER_CREDENTIALS = {"email": "other@example.com", "password": "another-pass-1"}
JD = "Backend Engineer: Python, FastAPI, Postgres. API design and databases."

LONG_ANSWER = (
    "I designed a rate-limited API gateway with token buckets backed by Redis, "
    "chose fail-closed behavior under store outage, and measured p99 latency "
    "before and after adding covering indexes on the hot lookup path."
)


async def _register(client, credentials: dict[str, str] = CREDENTIALS) -> None:
    response = await client.post("/api/auth/register", json=credentials)
    assert response.status_code == 201


async def _create_interview(client, dev_mode: bool = True) -> str:
    response = await client.post(
        "/api/interviews",
        json={"jd_text": JD, "dev_mode": dev_mode},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    return body["id"]


async def _answer_through_question(client, interview_id: str) -> None:
    # mock interviewer probes once on the first candidate answer per question
    probe = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": "I did some work on it."},
    )
    assert probe.status_code == 200
    assert probe.json()["awaiting_answer"] is True
    assert any(turn["is_probe"] for turn in probe.json()["turns"])

    advance = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": LONG_ANSWER},
    )
    assert advance.status_code == 200


async def test_create_requires_auth(client):
    response = await client.post(
        "/api/interviews",
        json={"jd_text": JD, "dev_mode": True},
    )
    assert response.status_code == 401


async def test_create_persists_questions(client):
    await _register(client)
    interview_id = await _create_interview(client, dev_mode=True)

    async with new_session() as db:
        interview = (
            await db.execute(
                select(Interview).where(Interview.id == uuid.UUID(interview_id))
            )
        ).scalar_one()
        question_count = (
            await db.execute(
                select(func.count())
                .select_from(Question)
                .where(Question.interview_id == interview.id)
            )
        ).scalar_one()
    assert interview.status.value == "ready"
    assert question_count == 3


async def test_full_mock_interview_lifecycle(client):
    await _register(client)
    interview_id = await _create_interview(client, dev_mode=True)

    start = await client.post(f"/api/interviews/{interview_id}/start")
    assert start.status_code == 200
    started = start.json()
    assert started["status"] == "in_progress"
    assert started["question_count"] == 3
    assert started["current_question_position"] == 0
    assert started["awaiting_answer"] is True
    assert started["current_question"]["text"]

    for _ in range(3):
        await _answer_through_question(client, interview_id)

    before_finish = await client.get(f"/api/interviews/{interview_id}")
    assert before_finish.json()["status"] == "in_progress"
    assert before_finish.json()["current_question_position"] == 2
    assert before_finish.json()["awaiting_answer"] is False

    finish = await client.post(f"/api/interviews/{interview_id}/finish")
    assert finish.status_code == 200
    assert finish.json()["status"] == "complete"

    report = await client.get(f"/api/interviews/{interview_id}/report")
    assert report.status_code == 200
    report_body = report.json()
    assert report_body["status"] == "complete"
    assert len(report_body["questions"]) == 3
    assert report_body["questions"][0]["answer_key"]["required_points"]
    assert report_body["questions"][0]["evaluation"]["scores"]["correctness"] >= 1

    async with new_session() as db:
        evaluation_count = (
            await db.execute(
                select(func.count())
                .select_from(QuestionEvaluation)
                .where(QuestionEvaluation.interview_id == uuid.UUID(interview_id))
            )
        ).scalar_one()
    assert evaluation_count == 3


async def test_answer_before_start_is_409(client):
    await _register(client)
    interview_id = await _create_interview(client)

    response = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": "Too early."},
    )
    assert response.status_code == 409


async def test_report_before_complete_is_409(client):
    await _register(client)
    interview_id = await _create_interview(client)
    await client.post(f"/api/interviews/{interview_id}/start")

    response = await client.get(f"/api/interviews/{interview_id}/report")
    assert response.status_code == 409


async def test_other_user_cannot_access_interview(client):
    await _register(client)
    interview_id = await _create_interview(client)

    await client.post("/api/auth/logout")
    await _register(client, OTHER_CREDENTIALS)

    for path in (
        f"/api/interviews/{interview_id}",
        f"/api/interviews/{interview_id}/start",
        f"/api/interviews/{interview_id}/report",
    ):
        if path.endswith("/start"):
            response = await client.post(path)
        else:
            response = await client.get(path)
        assert response.status_code == 404


async def _complete_interview(client, interview_id: str) -> None:
    start = await client.post(f"/api/interviews/{interview_id}/start")
    assert start.status_code == 200
    for _ in range(3):
        await _answer_through_question(client, interview_id)
    finish = await client.post(f"/api/interviews/{interview_id}/finish")
    assert finish.status_code == 200


async def test_list_requires_auth(client):
    response = await client.get("/api/interviews")
    assert response.status_code == 401


async def test_list_newest_first_with_scores(client):
    await _register(client)
    completed_id = await _create_interview(client)
    await _complete_interview(client, completed_id)
    ready_id = await _create_interview(client)

    response = await client.get("/api/interviews")
    assert response.status_code == 200
    interviews = response.json()["interviews"]
    assert [item["id"] for item in interviews] == [ready_id, completed_id]

    ready, completed = interviews
    assert ready["status"] == "ready"
    assert ready["overall_score"] is None
    assert ready["finished_at"] is None
    assert ready["question_count"] == 3
    # mock intake parses the profile synchronously at create time
    assert ready["role"]

    assert completed["status"] == "complete"
    assert 1 <= completed["overall_score"] <= 5
    assert completed["finished_at"] is not None
    assert completed["question_count"] == 3


async def test_list_only_shows_own_interviews(client):
    await _register(client)
    await _create_interview(client)

    await client.post("/api/auth/logout")
    await _register(client, OTHER_CREDENTIALS)

    response = await client.get("/api/interviews")
    assert response.status_code == 200
    assert response.json()["interviews"] == []


async def test_delete_me_cascades_interviews(client):
    await _register(client)
    await _create_interview(client)

    delete = await client.delete("/api/me")
    assert delete.status_code == 204

    async with new_session() as db:
        interview_count = (
            await db.execute(select(func.count()).select_from(Interview))
        ).scalar_one()
        user_count = (
            await db.execute(select(func.count()).select_from(User))
        ).scalar_one()
    assert interview_count == 0
    assert user_count == 0

    # recreate user so the truncate-after-test cleanup still has a valid session
    await _register(client)
