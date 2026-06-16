import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Interview,
    InterviewTurn,
    Question,
    QuestionEvaluation,
    SkillScore,
    TurnRole,
    User,
)
from app.schemas import EvidenceItem, Scores
from app.skills.schemas import SkillAnswerOut, SkillDetailOut, SkillOut, SkillsOut


def overall_score(scores: Scores) -> float:
    values = (
        scores.correctness,
        scores.depth,
        scores.structure,
        scores.communication,
    )
    return sum(values) / len(values)


def to_hundred(average: float) -> float:
    """Map a 1-5 score onto a 0-100 scale for display: 1->0, 3->50, 5->100.

    The judge still scores in 1-5 buckets; this is a presentation transform
    applied only at output boundaries, so storage and the eval harness stay in
    native units. It is affine, so a stored running average converts directly
    and a score difference (a trend) scales by 25.
    """
    return round(25 * average - 25, 1)


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


async def _tag_trends(db: AsyncSession, user_id: uuid.UUID) -> dict[str, float]:
    """Per tag: latest interview's average minus the previous interview's.

    Only tags judged in at least two interviews get a trend — one data
    point has no direction.
    """
    rows = (
        await db.execute(
            select(Question.tags, QuestionEvaluation.scores_json, Interview.created_at)
            .join(QuestionEvaluation, QuestionEvaluation.question_id == Question.id)
            .join(Interview, Interview.id == Question.interview_id)
            .where(Interview.user_id == user_id, Interview.deleted_at.is_(None))
        )
    ).all()

    # tag → interview created_at → overall scores in that interview
    by_tag: dict[str, dict[datetime, list[float]]] = {}
    for tags, scores_json, interview_created_at in rows:
        overall = overall_score(Scores(**scores_json))
        for tag in tags:
            by_tag.setdefault(tag, {}).setdefault(interview_created_at, []).append(
                overall
            )

    trends: dict[str, float] = {}
    for tag, by_interview in by_tag.items():
        if len(by_interview) < 2:
            continue
        ordered = sorted(by_interview)
        latest = by_interview[ordered[-1]]
        previous = by_interview[ordered[-2]]
        trends[tag] = sum(latest) / len(latest) - sum(previous) / len(previous)
    return trends


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
    trends = await _tag_trends(db, user.id)

    return SkillsOut(
        skills=[
            SkillOut(
                tag=row.tag,
                average=to_hundred(row.score_sum / row.evaluation_count),
                evaluation_count=row.evaluation_count,
                updated_at=row.updated_at,
                # a trend is a difference of 1-5 averages, so it scales by 25
                # onto the 0-100 scale (the offset cancels in a difference)
                trend=(
                    round(25 * trends[row.tag], 1) if row.tag in trends else None
                ),
            )
            for row in rows
        ]
    )


async def skill_detail(
    db: AsyncSession,
    user: User,
    tag: str,
) -> SkillDetailOut | None:
    """Every judged answer behind one tag's average — the receipts.

    Returns None when the user has no score for the tag.
    """
    skill_row = (
        await db.execute(
            select(SkillScore).where(
                SkillScore.user_id == user.id, SkillScore.tag == tag
            )
        )
    ).scalar_one_or_none()
    if skill_row is None:
        return None

    judged_rows = (
        await db.execute(
            select(Question, QuestionEvaluation, Interview)
            .join(QuestionEvaluation, QuestionEvaluation.question_id == Question.id)
            .join(Interview, Interview.id == Question.interview_id)
            .where(
                Interview.user_id == user.id,
                Interview.deleted_at.is_(None),
                Question.tags.any(tag),
            )
            .order_by(Interview.created_at.desc(), Question.position.asc())
        )
    ).all()

    question_ids = [question.id for question, _, _ in judged_rows]
    answers_by_question: dict[uuid.UUID, list[str]] = {}
    if question_ids:
        candidate_turns = (
            (
                await db.execute(
                    select(InterviewTurn)
                    .where(
                        InterviewTurn.question_id.in_(question_ids),
                        InterviewTurn.role == TurnRole.candidate,
                    )
                    .order_by(InterviewTurn.sequence.asc())
                )
            )
            .scalars()
            .all()
        )
        for turn in candidate_turns:
            answers_by_question.setdefault(turn.question_id, []).append(turn.content)

    return SkillDetailOut(
        tag=skill_row.tag,
        average=to_hundred(skill_row.score_sum / skill_row.evaluation_count),
        evaluation_count=skill_row.evaluation_count,
        answers=[
            SkillAnswerOut(
                interview_id=interview.id,
                interview_created_at=interview.created_at,
                position=question.position,
                qtype=question.qtype,
                question_text=question.text,
                candidate_answers=answers_by_question.get(question.id, []),
                scores=Scores(**evaluation.scores_json),
                evidence=[EvidenceItem(**item) for item in evaluation.evidence_json],
                missing_points=list(evaluation.missing_points_json),
                judge_model=evaluation.judge_model,
            )
            for question, evaluation, interview in judged_rows
        ],
    )


async def recompute_skill_scores(
    db: AsyncSession,
    user_id: uuid.UUID,
    tags: list[str],
) -> None:
    """Rebuild the given tags' running sums from surviving evaluations —
    called after an interview is soft-deleted so the averages keep
    agreeing with the visible receipts."""
    for tag in set(tags):
        rows = (
            await db.execute(
                select(QuestionEvaluation.scores_json)
                .join(Question, Question.id == QuestionEvaluation.question_id)
                .join(Interview, Interview.id == Question.interview_id)
                .where(
                    Interview.user_id == user_id,
                    Interview.deleted_at.is_(None),
                    Question.tags.any(tag),
                )
            )
        ).all()
        overalls = [overall_score(Scores(**scores_json)) for (scores_json,) in rows]

        existing = (
            await db.execute(
                select(SkillScore).where(
                    SkillScore.user_id == user_id, SkillScore.tag == tag
                )
            )
        ).scalar_one_or_none()
        if not overalls:
            if existing is not None:
                await db.delete(existing)
        elif existing is not None:
            existing.score_sum = sum(overalls)
            existing.evaluation_count = len(overalls)
            existing.updated_at = datetime.now(UTC)
        else:
            db.add(
                SkillScore(
                    user_id=user_id,
                    tag=tag,
                    score_sum=sum(overalls),
                    evaluation_count=len(overalls),
                    updated_at=datetime.now(UTC),
                )
            )


async def skill_average(
    db: AsyncSession,
    user_id: uuid.UUID,
    tag: str,
) -> float | None:
    """Current average on one tag — None when the user has no score yet."""
    row = (
        await db.execute(
            select(SkillScore).where(
                SkillScore.user_id == user_id, SkillScore.tag == tag
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.score_sum / row.evaluation_count


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
