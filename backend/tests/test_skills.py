import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import Interview, SkillScore, User
from app.db.session import new_session
from app.interviews import router as interviews_router
from app.interviews.service import InterviewService
from app.llm.mock import MockBackend
from app.schemas import Scores
from app.skills.service import load_skill_profile, overall_score, record_skill_scores

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "skills@example.com", "password": "correct-horse-9"}
JD = "Backend Engineer: Python, FastAPI, Postgres. API design and databases."

LONG_ANSWER = (
    "I designed a rate-limited API gateway with token buckets backed by Redis, "
    "chose fail-closed behavior under store outage, and measured p99 latency "
    "before and after adding covering indexes on the hot lookup path."
)

# mock judge: 33 words → level 2 → overall 2.0 on all four dimensions above
MOCK_OVERALL = 2.0


async def _register(client) -> None:
    response = await client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 201


async def _create_interview(client) -> str:
    response = await client.post(
        "/api/interviews",
        json={"jd_text": JD, "dev_mode": True},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _answer_through_question(client, interview_id: str) -> None:
    probe = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": "I did some work on it."},
    )
    assert probe.status_code == 200
    advance = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": LONG_ANSWER},
    )
    assert advance.status_code == 200


async def _finish_mock_interview(client) -> None:
    interview_id = await _create_interview(client)
    await client.post(f"/api/interviews/{interview_id}/start")
    for _ in range(3):
        await _answer_through_question(client, interview_id)
    finish = await client.post(f"/api/interviews/{interview_id}/finish")
    assert finish.status_code == 200


def test_overall_score_is_mean_of_four_dimensions():
    scores = Scores(correctness=4, depth=3, structure=4, communication=5)
    assert overall_score(scores) == 4.0


async def test_record_skill_scores_upserts_same_tag(client):
    await _register(client)
    async with new_session() as db:
        user = (await db.execute(select(User))).scalar_one()
        await record_skill_scores(
            db,
            user_id=user.id,
            tags=["databases/indexing"],
            scores=Scores(correctness=2, depth=2, structure=2, communication=2),
        )
        await record_skill_scores(
            db,
            user_id=user.id,
            tags=["databases/indexing"],
            scores=Scores(correctness=4, depth=4, structure=4, communication=4),
        )
        await db.commit()
        row = (
            await db.execute(
                select(SkillScore).where(
                    SkillScore.user_id == user.id,
                    SkillScore.tag == "databases/indexing",
                )
            )
        ).scalar_one()
    assert row.evaluation_count == 2
    assert row.score_sum == pytest.approx(6.0)
    assert row.score_sum / row.evaluation_count == pytest.approx(3.0)


async def test_record_skill_scores_full_score_per_tag(client):
    await _register(client)
    async with new_session() as db:
        user = (await db.execute(select(User))).scalar_one()
        await record_skill_scores(
            db,
            user_id=user.id,
            tags=["databases/indexing", "databases/transactions"],
            scores=Scores(correctness=4, depth=4, structure=4, communication=4),
        )
        await db.commit()
        rows = (
            await db.execute(
                select(SkillScore).where(SkillScore.user_id == user.id)
            )
        ).scalars().all()
    assert len(rows) == 2
    assert {row.tag for row in rows} == {
        "databases/indexing",
        "databases/transactions",
    }
    assert all(row.score_sum == pytest.approx(4.0) for row in rows)


async def test_finish_aggregates_skills_from_mock_interview(client):
    await _register(client)
    await _finish_mock_interview(client)

    skills = await client.get("/api/skills")
    assert skills.status_code == 200
    body = skills.json()["skills"]
    assert len(body) == 3
    tags = {item["tag"] for item in body}
    assert tags == {
        "behavioral/ownership",
        "databases/indexing",
        "system_design/rate-limiting",
    }
    assert all(item["average"] == pytest.approx(MOCK_OVERALL) for item in body)
    assert all(item["evaluation_count"] == 1 for item in body)


async def test_same_tag_accumulates_across_two_interviews(client):
    await _register(client)
    await _finish_mock_interview(client)
    await _finish_mock_interview(client)

    skills = await client.get("/api/skills")
    ownership = next(
        item for item in skills.json()["skills"] if item["tag"] == "behavioral/ownership"
    )
    assert ownership["evaluation_count"] == 2
    assert ownership["average"] == pytest.approx(MOCK_OVERALL)


async def test_skills_sorted_weakest_first(client):
    await _register(client)
    await _finish_mock_interview(client)

    async with new_session() as db:
        user = (await db.execute(select(User))).scalar_one()
        await record_skill_scores(
            db,
            user_id=user.id,
            tags=["zzzz/weak"],
            scores=Scores(correctness=1, depth=1, structure=1, communication=1),
        )
        await db.commit()

    skills = await client.get("/api/skills")
    assert skills.status_code == 200
    tags = [item["tag"] for item in skills.json()["skills"]]
    assert tags[0] == "zzzz/weak"
    assert skills.json()["skills"][0]["average"] == pytest.approx(1.0)


async def test_skills_requires_auth(client):
    assert (await client.get("/api/skills")).status_code == 401


class CapturingMockBackend(MockBackend):
    skill_profiles: list[dict[str, float]] = []

    async def generate(self, profile, skill_profile, n_questions):
        type(self).skill_profiles.append(dict(skill_profile))
        return await super().generate(profile, skill_profile, n_questions)


async def test_load_skill_profile_returns_weakest_three(client):
    await _register(client)
    async with new_session() as db:
        user = (await db.execute(select(User))).scalar_one()
        for tag, average in (
            ("aaa/strong", 4.0),
            ("bbb/mid", 3.0),
            ("ccc/weak", 2.0),
            ("ddd/weaker", 1.0),
        ):
            await record_skill_scores(
                db,
                user_id=user.id,
                tags=[tag],
                scores=Scores(
                    correctness=int(average),
                    depth=int(average),
                    structure=int(average),
                    communication=int(average),
                ),
            )
        await db.commit()
        profile = await load_skill_profile(db, user.id, limit=3)

    assert list(profile.keys()) == ["ddd/weaker", "ccc/weak", "bbb/mid"]
    assert profile["ddd/weaker"] == pytest.approx(1.0)


async def test_second_interview_passes_weakest_skill_profile(client, monkeypatch):
    capturing = CapturingMockBackend()
    monkeypatch.setattr(interviews_router, "_service", InterviewService(llm=capturing))

    await _register(client)
    await _finish_mock_interview(client)
    CapturingMockBackend.skill_profiles.clear()

    await _create_interview(client)

    assert len(CapturingMockBackend.skill_profiles) == 1
    passed = CapturingMockBackend.skill_profiles[0]
    assert len(passed) == 3
    assert passed["behavioral/ownership"] == pytest.approx(MOCK_OVERALL)
    assert passed["databases/indexing"] == pytest.approx(MOCK_OVERALL)
    assert passed["system_design/rate-limiting"] == pytest.approx(MOCK_OVERALL)


async def test_delete_me_cascades_skill_scores(client):
    await _register(client)
    await _finish_mock_interview(client)

    delete = await client.delete("/api/me")
    assert delete.status_code == 204

    async with new_session() as db:
        skill_count = (
            await db.execute(select(func.count()).select_from(SkillScore))
        ).scalar_one()
        interview_count = (
            await db.execute(select(func.count()).select_from(Interview))
        ).scalar_one()
    assert skill_count == 0
    assert interview_count == 0

    await _register(client)
