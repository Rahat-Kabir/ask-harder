from fastapi import APIRouter, HTTPException, status

from app.auth.deps import CurrentUser, DbSession
from app.skills.schemas import SkillDetailOut, SkillsOut
from app.skills.service import list_skills, skill_detail

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=SkillsOut)
async def get_skills(user: CurrentUser, db: DbSession) -> SkillsOut:
    return await list_skills(db, user)


# `:path` because tags contain slashes ("databases/indexing")
@router.get("/skills/{tag:path}", response_model=SkillDetailOut)
async def get_skill_detail(
    tag: str, user: CurrentUser, db: DbSession
) -> SkillDetailOut:
    detail = await skill_detail(db, user, tag)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    return detail
