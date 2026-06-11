import json
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.llm.errors import (
    IntakeParseError,
    LlmEmptyResponse,
    LlmValidationError,
)
from app.llm.prompts import INTAKE_SYSTEM_PROMPT, plan_system_prompt
from app.schemas import (
    AnswerKey,
    Plan,
    PlannedQuestion,
    Profile,
    QuestionType,
)

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)

MAX_JSON_ATTEMPTS = 2


class _UnusableJdResponse(BaseModel):
    error: str


class _ProfileResponse(BaseModel):
    role: str
    seniority: str
    stack: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    resume_claims: list[str] = Field(default_factory=list)


class _PlannedQuestionResponse(BaseModel):
    qtype: QuestionType
    text: str
    tags: list[str] = Field(default_factory=list)
    answer_key: AnswerKey


class _PlanResponse(BaseModel):
    questions: list[_PlannedQuestionResponse]


class DeepSeekJsonClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaModel],
    ) -> SchemaModel:
        last_error: Exception | None = None
        for _ in range(MAX_JSON_ATTEMPTS):
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=self._max_tokens,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                last_error = LlmEmptyResponse("DeepSeek returned empty content")
                continue
            try:
                payload = json.loads(content)
                return schema.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as error:
                last_error = LlmValidationError(str(error))
        if last_error is None:
            raise LlmEmptyResponse("DeepSeek returned empty content")
        raise last_error


class DeepSeekIntakeParser:
    def __init__(self, client: DeepSeekJsonClient) -> None:
        self._client = client

    async def parse(self, jd_text: str, resume_text: str | None = None) -> Profile:
        user_prompt = f"Job description:\n{jd_text.strip()}"
        if resume_text and resume_text.strip():
            user_prompt += f"\n\nResume:\n{resume_text.strip()}"

        try:
            parsed = await self._client.complete_json(
                system_prompt=INTAKE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_ProfileResponse,
            )
        except LlmValidationError as error:
            if "unusable_jd" in str(error):
                raise IntakeParseError(
                    "Could not parse the job description. Try a clearer JD."
                ) from error
            raise IntakeParseError(
                "Could not parse the job description. Try a clearer JD."
            ) from error
        except LlmEmptyResponse as error:
            raise IntakeParseError(
                "Could not parse the job description. Try a clearer JD."
            ) from error

        if not parsed.role.strip() or not parsed.seniority.strip():
            raise IntakeParseError(
                "Could not parse the job description. Try a clearer JD."
            )

        return Profile(
            role=parsed.role.strip(),
            seniority=parsed.seniority.strip(),
            stack=[item.strip() for item in parsed.stack if item.strip()],
            competencies=[item.strip() for item in parsed.competencies if item.strip()],
            resume_claims=[
                item.strip() for item in parsed.resume_claims if item.strip()
            ],
        )


class DeepSeekPlanGenerator:
    def __init__(self, client: DeepSeekJsonClient) -> None:
        self._client = client

    async def generate(
        self,
        profile: Profile,
        skill_profile: dict[str, float],
        n_questions: int,
    ) -> Plan:
        dev_mode = n_questions == 3
        weakest_tags = sorted(skill_profile, key=skill_profile.get)[:3]
        user_prompt = (
            f"Candidate profile JSON:\n{profile.model_dump_json()}\n\n"
            f"Question count: {n_questions}\n"
            f"Weakest skill tags (prioritize when relevant): {weakest_tags or 'none'}"
        )

        try:
            parsed = await self._client.complete_json(
                system_prompt=plan_system_prompt(n_questions, dev_mode),
                user_prompt=user_prompt,
                schema=_PlanResponse,
            )
        except (LlmEmptyResponse, LlmValidationError) as error:
            raise LlmValidationError(
                f"Plan generation failed validation: {error}"
            ) from error

        if len(parsed.questions) != n_questions:
            raise LlmValidationError(
                f"Expected {n_questions} questions, got {len(parsed.questions)}"
            )

        questions = [
            PlannedQuestion(
                position=index,
                qtype=question.qtype,
                text=question.text.strip(),
                tags=[tag.strip() for tag in question.tags if tag.strip()],
                answer_key=question.answer_key,
            )
            for index, question in enumerate(parsed.questions)
        ]
        return Plan(questions=questions)
