from fastapi import APIRouter

from app.auth.deps import CurrentUser, DbSession
from app.skills.schemas import SkillsOut
from app.skills.service import list_skills

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=SkillsOut)
async def get_skills(user: CurrentUser, db: DbSession) -> SkillsOut:
    return await list_skills(db, user)
