import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SkillScore, User
from app.schemas import Scores
from app.skills.schemas import SkillOut, SkillsOut


def overall_score(scores: Scores) -> float:
    values = (
        scores.correctness,
        scores.depth,
        scores.structure,
        scores.communication,
    )
    return sum(values) / len(values)


async def record_skill_scores(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tags: list[str],
    scores: Scores,
) -> None:
    """Upsert per-tag running averages after one judged answer.

    Each non-empty tag on the question receives the full overall score —
    a multi-tag question counts the same performance toward every tag.
    """
    overall = overall_score(scores)
    now = datetime.now(UTC)
    for raw_tag in tags:
        tag = raw_tag.strip()
        if not tag:
            continue
        insert_stmt = insert(SkillScore).values(
            user_id=user_id,
            tag=tag,
            score_sum=overall,
            evaluation_count=1,
            updated_at=now,
        )
        upsert = insert_stmt.on_conflict_do_update(
            constraint="uq_skill_scores_user_tag",
            set_={
                "score_sum": SkillScore.score_sum + insert_stmt.excluded.score_sum,
                "evaluation_count": (
                    SkillScore.evaluation_count + insert_stmt.excluded.evaluation_count
                ),
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        await db.execute(upsert)


async def list_skills(db: AsyncSession, user: User) -> SkillsOut:
    rows = (
        (
            await db.execute(
                select(SkillScore)
                .where(SkillScore.user_id == user.id)
                .order_by(
                    (SkillScore.score_sum / SkillScore.evaluation_count).asc(),
                    SkillScore.tag.asc(),
                )
            )
        )
        .scalars()
        .all()
    )

    return SkillsOut(
        skills=[
            SkillOut(
                tag=row.tag,
                average=row.score_sum / row.evaluation_count,
                evaluation_count=row.evaluation_count,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    )


async def load_skill_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 3,
) -> dict[str, float]:
    """Weakest tags first — fed to the planner on the next interview."""
    rows = (
        (
            await db.execute(
                select(SkillScore)
                .where(SkillScore.user_id == user_id)
                .order_by(
                    (SkillScore.score_sum / SkillScore.evaluation_count).asc(),
                    SkillScore.tag.asc(),
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {row.tag: row.score_sum / row.evaluation_count for row in rows}
