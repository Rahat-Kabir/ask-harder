from datetime import datetime

from pydantic import BaseModel, Field


class SkillOut(BaseModel):
    tag: str
    average: float = Field(ge=1.0, le=5.0)
    evaluation_count: int = Field(ge=1)
    updated_at: datetime


class SkillsOut(BaseModel):
    skills: list[SkillOut]
