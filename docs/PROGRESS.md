# Progress

Build status for ask-harder v1.

## Status

| # | Milestone | Status | Notes |
|---|---|---|---|
| 1 | Skeleton (FastAPI, compose, schema, Alembic, auth, React shell) | **done** | Full-stack foundation verified end-to-end |
| 2 | Mock flow (state machine, SSE chat, report) | **done** | Runnable without API keys |
| 3 | Intake + plan (real DeepSeek, validated JSON) | **done** | |
| 4 | Interviewer (streaming, probe logic) | **done** | |
| 5 | Judge (Sonnet structured output, evidence validation) | **done** | |
| 6 | Eval harness (fixtures, 4 suites, comparison, /methodology) | **in progress** | Harness built; Sonnet re-run and `/methodology` page remain |
| 7 | Skill tracking (aggregates, dashboard, planner reads weak tags) | not started | |
| 8 | Polish + ship (deploy, demo video, README) | not started | |

## v1 definition

A stranger can register, paste a JD, take a 7-question interview, and get
an evidence-grounded report at a public URL — and `/methodology` shows
passing eval results.

## Architecture decisions

**Foundation**

- uv monorepo layout: `backend/` (FastAPI) + `frontend/` (Vite/React).
- Dev runs Postgres in Docker; app runs natively with hot reload.
- SQLAlchemy 2.0 over SQLModel — Postgres-native types and Alembic autogen
  are first-class; API schemas stay as separate Pydantic models.
- Tables added with the feature that needs them, not all upfront.
- Auth: argon2-cffi, DB-backed sessions (sha256 of cookie token, never the
  token), generic login errors, HTTP-only cookies.
- All JSON routes under `/api`; SPA and API share one origin in prod.
  Vite dev proxy avoids CORS for session cookies.

**LLM pipeline**

- Four LLM components as Protocols with typed I/O in `app/schemas.py`.
- **Context starvation at the type level**: Interviewer gets `InterviewQuestion`
  (no answer key); Judge gets `PlannedQuestion` (with key).
- MockBackend drives the full flow deterministically for tests and offline dev.
- Interview state machine with probe cap (max 2), SSE streaming, and REST +
  report endpoints.
- `LLM_BACKEND=mock|deepseek`: composite routes real intake/plan/interviewer/
  judge when keys are set; mock stays sync, deepseek intake runs async
  (`preparing` → `ready` | `abandoned`).
- Judge post-validates verbatim quotes (retry once, then strip) and filters
  `missing_points` to answer-key strings.
- LLM modules are role-named (`intake.py`, `interviewer.py`, `judge.py`);
  provider-specific logic lives in provider-named classes.

**Eval harness**

- `backend/evals/`: 10 fixtures × bad/mediocre/strong answers, four assertion
  suites (ordering, stability, grounding, key adherence).
- Evals assert on raw judge output — production `evaluate()` strips/filters,
  which would make grounding suites pass by construction.
- Results artifact at `evals/results/<judge>.json` — data source for the
  planned `/methodology` page.

## Eval findings

First Sonnet run (43/52, zero fabrication) surfaced two systematic issues:
(1) grounding failures were ellipsis splices, not invented quotes; (2) key
adherence at 71% because the model appended commentary to key strings.
Prompt and validator fixes applied — one contiguous span per quote,
character-for-character `missing_points`, segment-wise grounding for
ellipsis-spliced quotes. Sonnet re-run pending to verify before closing M6.

## Known limitations

- FastAPI TestClient emits a Starlette deprecation warning about `httpx2`;
  revisit when bumping httpx.
- Expired session rows are never purged (harmless until scale).
- No rate limiting on login/register (revisit before public launch).

## Next up

- `run_comparison.py` (Batches API) and `/methodology` page (renders
  `evals/results/*.json`).
- Re-run all eval suites on Sonnet to verify the prompt/validator fixes.
