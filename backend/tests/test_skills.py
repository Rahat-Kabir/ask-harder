import pytest
from sqlalchemy import func, select

from app.db.models import Interview, SkillScore, User
from app.db.session import new_session
from app.interviews import router as interviews_router
from app.interviews.service import InterviewService
from app.llm.mock import MockBackend
from app.schemas import Scores
from app.skills.service import (
    load_skill_profile,
    overall_score,
    record_skill_scores,
    to_hundred,
)

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

# 56 words with the probe reply — mock judge level 3 → overall 3.0
BETTER_ANSWER = (
    "I designed a rate-limited API gateway with token buckets backed by Redis, "
    "chose fail-closed behavior under store outage, and measured p99 latency "
    "before and after adding covering indexes on the hot lookup path. "
    "I also documented the failure modes, added alerting on rejection rates, "
    "and load-tested the limiter at ten times the expected peak traffic."
)
BETTER_OVERALL = 3.0


async def _register(client) -> None:
    response = await client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 201


async def _create_interview(client) -> str:
    response = await client.post(
        "/api/interviews",
        json={"jd_text": JD, "session_type": "screen"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _answer_through_question(
    client, interview_id: str, answer: str = LONG_ANSWER
) -> None:
    probe = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": "I did some work on it."},
    )
    assert probe.status_code == 200
    advance = await client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"text": answer},
    )
    assert advance.status_code == 200


async def _finish_mock_interview(client, answer: str = LONG_ANSWER) -> str:
    interview_id = await _create_interview(client)
    await client.post(f"/api/interviews/{interview_id}/start")
    for _ in range(3):
        await _answer_through_question(client, interview_id, answer)
    finish = await client.post(f"/api/interviews/{interview_id}/finish")
    assert finish.status_code == 200
    return interview_id


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
            (await db.execute(select(SkillScore).where(SkillScore.user_id == user.id)))
            .scalars()
            .all()
        )
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
    assert all(
        item["average"] == pytest.approx(to_hundred(MOCK_OVERALL)) for item in body
    )
    assert all(item["evaluation_count"] == 1 for item in body)


async def test_same_tag_accumulates_across_two_interviews(client):
    await _register(client)
    await _finish_mock_interview(client)
    await _finish_mock_interview(client)

    skills = await client.get("/api/skills")
    ownership = next(
        item
        for item in skills.json()["skills"]
        if item["tag"] == "behavioral/ownership"
    )
    assert ownership["evaluation_count"] == 2
    assert ownership["average"] == pytest.approx(to_hundred(MOCK_OVERALL))


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
    assert skills.json()["skills"][0]["average"] == pytest.approx(to_hundred(1.0))


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


async def test_trend_null_with_single_interview(client):
    await _register(client)
    await _finish_mock_interview(client)

    skills = await client.get("/api/skills")
    assert skills.status_code == 200
    assert all(item["trend"] is None for item in skills.json()["skills"])


async def test_trend_is_latest_minus_previous_interview(client):
    await _register(client)
    await _finish_mock_interview(client, answer=LONG_ANSWER)  # 2.0 per tag
    await _finish_mock_interview(client, answer=BETTER_ANSWER)  # 3.0 per tag

    skills = await client.get("/api/skills")
    assert skills.status_code == 200
    for item in skills.json()["skills"]:
        # a trend is a difference of 1-5 averages, scaled by 25 onto 0-100
        assert item["trend"] == pytest.approx(25 * (BETTER_OVERALL - MOCK_OVERALL))


async def test_delete_interview_recomputes_skill_scores(client):
    await _register(client)
    await _finish_mock_interview(client, answer=LONG_ANSWER)  # 2.0 per tag
    better_id = await _finish_mock_interview(client, answer=BETTER_ANSWER)  # 3.0

    before = await client.get("/api/skills")
    indexing = next(
        s for s in before.json()["skills"] if s["tag"] == "databases/indexing"
    )
    assert indexing["evaluation_count"] == 2
    assert indexing["average"] == pytest.approx(to_hundred(2.5))

    delete = await client.delete(f"/api/interviews/{better_id}")
    assert delete.status_code == 204

    after = await client.get("/api/skills")
    indexing = next(
        s for s in after.json()["skills"] if s["tag"] == "databases/indexing"
    )
    assert indexing["evaluation_count"] == 1
    assert indexing["average"] == pytest.approx(to_hundred(MOCK_OVERALL))

    # receipts agree with the recomputed number
    detail = await client.get("/api/skills/databases/indexing")
    assert len(detail.json()["answers"]) == 1


async def test_deleting_last_judged_interview_removes_tags(client):
    await _register(client)
    interview_id = await _finish_mock_interview(client)

    delete = await client.delete(f"/api/interviews/{interview_id}")
    assert delete.status_code == 204

    skills = await client.get("/api/skills")
    assert skills.json()["skills"] == []
    assert (await client.get("/api/skills/databases/indexing")).status_code == 404


async def test_skill_detail_requires_auth(client):
    assert (await client.get("/api/skills/databases/indexing")).status_code == 401


async def test_skill_detail_unknown_tag_is_404(client):
    await _register(client)
    assert (await client.get("/api/skills/nope/never")).status_code == 404


async def test_skill_detail_returns_judged_answers(client):
    await _register(client)
    await _finish_mock_interview(client)

    response = await client.get("/api/skills/databases/indexing")
    assert response.status_code == 200
    body = response.json()
    assert body["tag"] == "databases/indexing"
    assert body["average"] == pytest.approx(to_hundred(MOCK_OVERALL))
    assert body["evaluation_count"] == 1

    assert len(body["answers"]) == 1
    answer = body["answers"][0]
    assert "index" in answer["question_text"]
    assert answer["qtype"] == "technical"
    # both candidate turns on the question: the probe reply, then the real answer
    assert answer["candidate_answers"] == ["I did some work on it.", LONG_ANSWER]
    # mock judge at level 2: correctness/structure 2, depth 1, communication 3
    assert answer["scores"] == {
        "correctness": 2,
        "depth": 1,
        "structure": 2,
        "communication": 3,
    }
    assert answer["judge_model"] == "mock"
    assert isinstance(answer["evidence"], list)
    assert isinstance(answer["missing_points"], list)


async def test_skill_detail_newest_interview_first(client):
    await _register(client)
    await _finish_mock_interview(client)
    await _finish_mock_interview(client)

    response = await client.get("/api/skills/databases/indexing")
    assert response.status_code == 200
    answers = response.json()["answers"]
    assert len(answers) == 2
    assert answers[0]["interview_id"] != answers[1]["interview_id"]
    assert answers[0]["interview_created_at"] >= answers[1]["interview_created_at"]


async def test_skill_detail_does_not_leak_other_users(client):
    await _register(client)
    await _finish_mock_interview(client)
    await client.post("/api/auth/logout")

    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "correct-horse-9"},
    )
    assert other.status_code == 201
    # the other user has no score for the tag, so the first user's
    # answers must not be reachable at all
    assert (await client.get("/api/skills/databases/indexing")).status_code == 404


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
