import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# resumes go into paid LLM prompts — cap them so one request can't run up
# the bill. ~20k chars is several pages; frontend textareas mirror this.
MAX_RESUME_CHARS = 20_000


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime
    resume_text: str | None = None


class ResumeIn(BaseModel):
    # null or blank clears the saved resume
    resume_text: str | None = Field(default=None, max_length=MAX_RESUME_CHARS)
