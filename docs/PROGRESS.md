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
| 6 | Eval harness (fixtures, 4 suites, comparison, /methodology) | **in progress** | Harness + `/methodology` page built; Sonnet re-run and comparison remain |
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
- 2026-06-11 — Tooling + cleanup slice: **ruff** (lint `E,F,W,I,UP,B,SIM` +
  format; `prompts.py` exempt from E501 — rewrapping prompt text would
  change the prompts), whole backend reformatted, enums → `StrEnum`,
  `raise ... from` in routers. **CI** (GitHub Actions): ruff + pytest
  (Postgres 17 service) + mock evals + frontend lint/build on every push.
  Code smells fixed: background prep tasks held in a strong-reference set
  (GC safety); `turns.sequence` column (0-based per interview, unique,
  backfilled in migration `b7c8d9e0f1a2`) replaces fabricated created_at
  microsecond offsets as turn ordering; duplicate excepts collapsed to
  `except LlmError`; `_judge_model_name` simplified.

- 2026-06-12 — First real dogfood run (7-question AI-developer JD, DeepSeek +
  Sonnet, end-to-end to report). Pipeline held: plan tailored to the JD, all
  evidence quotes verbatim, missing points all from the frozen keys. Findings:
  (1) `[[DONE]]` sentinel leaks into chat UI when split across stream chunks;
  (2) Finish button never appears — `interviewer_done` SSE handler sets
  `awaitingAnswer` unconditionally and `submitAnswer` never corrects it;
  (3) report hid `strong_signals`/`red_flags`; (4) judge model answers can
  contain placeholder variables ("X tasks, Y%"). **All four fixed**:
  marker-aware `strip_done_marker()` stream filter (buffers partial-marker
  tails, 5 new unit tests); `interviewer_done` only awaits an answer when
  the interviewer actually spoke + `submitAnswer` syncs from the
  authoritative POST response; ReportPage renders all three key sections;
  judge prompt forbids placeholder variables in model answers.
- 2026-06-12 — Interview-flow fixes verified in a real browser ($0):
  isolated mock stack (uvicorn :8001 + vite :5175; `VITE_API_TARGET` env
  added to the vite proxy for exactly this), full 3-question dev-mode
  interview driven by Playwright. Finish button appeared unprompted after
  the last answer, no phantom interviewer bubble, finish → report
  auto-navigation worked, report shows all three answer-key sections.
  Still needing a real DeepSeek run to verify: the `[[DONE]]` stream fix
  and the no-placeholder model-answer prompt rule.

- 2026-06-12 — `/methodology` built ($0): `GET /api/methodology` (no auth)
  serves the committed `evals/results/*.json` validated through pydantic;
  public `/methodology` SPA route (router now wraps both auth states so the
  page works logged-out) explains the four suites and renders per-judge
  cards (ordering n/n, grounding %, adherence %, run date). Verified in a
  clean Playwright browser with no session.   Real-judge numbers appear
  automatically once the deferred Sonnet re-run writes `anthropic.json`.

- 2026-06-12 — DeepSeek v4 env config: per-role model ids
  (`DEEPSEEK_*_MODEL`), global thinking toggle (`DEEPSEEK_THINKING`),
  and reasoning effort (`DEEPSEEK_REASONING_EFFORT`) wired through
  `deepseek_common.py` to intake, plan, and interviewer. Interviewer
  streams only `content` deltas (reasoning stays hidden). `.env.example`
  updated with v4 examples.

## Known limitations

- FastAPI TestClient emits a Starlette deprecation warning about `httpx2`;
  revisit when bumping httpx.
- Expired session rows are never purged (harmless until scale).
- No rate limiting on login/register (revisit before public launch).

## Next up

- `run_comparison.py` (Batches API) and `/methodology` page (renders
  `evals/results/*.json`).
- Re-run all eval suites on Sonnet to verify the prompt/validator fixes.
