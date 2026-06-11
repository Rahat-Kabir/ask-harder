from anthropic import AsyncAnthropic

from app.llm.errors import LlmEmptyResponse, LlmValidationError
from app.llm.judge_common import (
    build_judge_user_prompt,
    filter_missing_points,
    validate_evidence,
)
from app.llm.prompts import JUDGE_SYSTEM_PROMPT
from app.schemas import Evaluation, PlannedQuestion, Turn

MAX_JUDGE_ATTEMPTS = 2

_GROUNDING_RETRY_NOTE = (
    "\n\nYour previous response included evidence quotes that were not verbatim "
    "substrings of the candidate's words. Regenerate the evaluation. Every "
    "evidence.quote MUST be copied exactly from candidate role lines in the "
    "transcript."
)


class AnthropicJudge:
    judge_model_name: str

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self.judge_model_name = model

    async def evaluate(
        self,
        question: PlannedQuestion,
        turns: list[Turn],
    ) -> Evaluation:
        user_prompt = build_judge_user_prompt(
            question.text, question.answer_key, turns
        )
        last_evaluation: Evaluation | None = None

        for attempt in range(MAX_JUDGE_ATTEMPTS):
            prompt = user_prompt
            if attempt > 0:
                prompt += _GROUNDING_RETRY_NOTE

            evaluation = await self._call_parse(prompt)

            validated_evidence, all_grounded = validate_evidence(
                turns, evaluation.evidence
            )
            filtered_missing = filter_missing_points(
                evaluation.missing_points, question.answer_key
            )
            evaluation = evaluation.model_copy(
                update={
                    "evidence": validated_evidence,
                    "missing_points": filtered_missing,
                }
            )
            last_evaluation = evaluation
            if all_grounded:
                return evaluation

        assert last_evaluation is not None
        return last_evaluation

    async def evaluate_raw(
        self,
        question: PlannedQuestion,
        turns: list[Turn],
    ) -> Evaluation:
        """One model call, no grounding retry, no post-validation.

        Exists for the eval harness: evaluate() strips ungrounded evidence
        and filters missing_points, which would make grounding/adherence
        evals pass by construction. Production code must use evaluate().
        """
        return await self._call_parse(
            build_judge_user_prompt(question.text, question.answer_key, turns)
        )

    async def _call_parse(self, user_prompt: str) -> Evaluation:
        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            output_format=Evaluation,
        )
        if response.parsed_output is None:
            raise LlmEmptyResponse("Anthropic judge returned no parsed output")
        try:
            return Evaluation.model_validate(response.parsed_output.model_dump())
        except Exception as error:
            raise LlmValidationError(str(error)) from error
