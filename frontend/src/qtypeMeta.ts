import type { QuestionType } from './api'

// What axis each question type is scored on — shown to the candidate before
// they answer and again on the report, so a behavioral warmup isn't answered
// like a technical deep-dive. Deliberately category-level (the shape of a good
// answer), never the specific frozen rubric, so it doesn't leak the key.
export const QUESTION_TYPE_INTENT: Record<QuestionType, string> = {
  warmup:
    'Scored like a story: a concrete project, your role, and the outcome — not deep implementation detail.',
  behavioral:
    'Scored on ownership and judgment: what you did, why, the result, and what you learned.',
  technical:
    'Scored on correctness and depth: the right answer, the trade-offs, and the failure modes.',
  system_design:
    'Scored on structure and trade-offs: your approach, where state lives, and how it fails.',
}
