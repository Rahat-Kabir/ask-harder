# Tech Spec (as-built)

What actually exists, updated as it changes.

## Stack (as of milestone 1)

- Python 3.13 (pinned in `backend/.python-version`), uv-managed.
- FastAPI + uvicorn. Single package, src layout: project `ask-harder-backend`,
  import name `app` (`uvicorn app.main:app`).
- Postgres 17 via docker-compose (dev: only postgres is containerized; the
  app runs natively with `uvicorn --reload`).
- Config: pydantic-settings (`app/config.py`) reads the **repo-root** `.env`;
  in prod the file is absent and real env vars take over. `DATABASE_URL` is
  required — startup fails fast without it. DeepSeek model ids are per-role
  (`DEEPSEEK_INTAKE_MODEL`, `DEEPSEEK_PLAN_MODEL`, `DEEPSEEK_INTERVIEWER_MODEL`);
  v4 thinking is one global switch (`DEEPSEEK_THINKING`, `DEEPSEEK_REASONING_EFFORT`).
  Anthropic judge model via `ANTHROPIC_JUDGE_MODEL`. See `.env.example`.
- DB: SQLAlchemy 2.0 typed ORM (`Mapped[]`), async engine on asyncpg.
  `app/db/base.py` defines `Base` with a constraint **naming convention**;
  `app/db/session.py` exposes `get_session()` (one session per request,
  `expire_on_commit=False`). Models in `app/db/models.py`.
- Migrations: Alembic (async template) in `backend/alembic/`. `env.py` pulls
  the URL from app settings and metadata from `Base` — `alembic.ini` holds no
  URL. Every schema change ships as a migration; no `create_all`.
- Tests: pytest + FastAPI TestClient, in `backend/tests/`.
- Frontend: Vite +   React 19 + TypeScript in `frontend/`. `api.ts` is the
  single typed fetch wrapper. Dev: Vite proxies `/api` → `127.0.0.1:8000`
  (same-origin, cookies work, no CORS). `react-router-dom` routes:
  `/`, `/interviews/new`, `/interviews/:id`, `/interviews/:id/report`,
  `/skills`, `/skills/*` (splat, not `:tag` — tags contain slashes),
  `/profile` (account stats client-side from existing endpoints + delete
  account via `DELETE /api/me`; header email links here).
  Chat page uses `EventSource` on `/api/interviews/:id/stream`.
- URL scheme: **all API routes under `/api`**; `/health` unprefixed (infra
  probes). Page routes and API routes must never share a path — prod serves
  the SPA and API from one origin.

## LLM components

- All LLM I/O is typed (`app/schemas.py`); no raw-string parsing anywhere.
- Four components as `@runtime_checkable` Protocols
  (`app/llm/interfaces.py`): IntakeParser, PlanGenerator, Interviewer,
  Judge. `LLM_BACKEND` config (`mock`|`deepseek`): mock = all four on
  `MockBackend`; deepseek = `DeepSeekIntakeParser` + `DeepSeekPlanGenerator`
  (OpenAI-compatible API, JSON mode, Pydantic validation) wired through
  `CompositeLlmBackend` with `DeepSeekInterviewer` + `AnthropicJudge`
  (Claude Sonnet 4.6, `messages.parse()`). DeepSeek v4 thinking mode
  (`extra_body.thinking`, `reasoning_effort`) is built in `deepseek_common.py`
  and applied to intake, plan, and interviewer from env.
- Context starvation is type-enforced: Interviewer receives
  `InterviewQuestion` (no answer_key field), Judge receives
  `PlannedQuestion` (with key). `PlannedQuestion.public()` strips the key.
- Interviewer: `stream_respond()` yields token deltas; `respond()` accumulates.
  DeepSeek uses `[[DONE]]` to signal advance; backend `parse_interviewer_output()`
  enforces max 2 probes. Planned questions stream in fixed-size chunks on
  `start`/advance (no LLM call).
- Judge: `AnthropicJudge` calls `messages.parse(output_format=Evaluation)` with
  adaptive thinking. Post-validation in `judge_common`: evidence quotes must be
  verbatim substrings of candidate turns (one retry, then strip invalid quotes);
  `missing_points` filtered to answer-key strings. `judge_model` column stores
  the Anthropic model id (e.g. `claude-sonnet-4-6`).
- Eval harness (`backend/evals/`): four suites (ordering,
  stability, grounding, key adherence) over 10 committed fixtures (question
  + answer key + bad/mediocre/strong answers). Judge selected via
  `EVAL_JUDGE` env (`mock` default, `anthropic`). Evals assert on
  `evaluate_raw()` — one un-validated model call — because the production
  `evaluate()` pipeline would make grounding/adherence pass by construction.
  Each session writes `evals/results/<judge>.json` (the `/methodology` data
  source). Stability is marker-gated (`-m "not stability"` skips its 60
  extra calls). See `docs/testing.md` for how to run.

## Auth

- Passwords: argon2 via argon2-cffi (rehash-on-login when params change).
- Sessions: DB-backed. Cookie holds a random 256-bit token; the `sessions`
  table stores its **sha256** (a DB leak yields no usable tokens). Cookie is
  HTTP-only, SameSite=lax, `secure` outside dev, TTL 14 days
  (`SESSION_TTL_DAYS`).
- `get_current_user` dependency: cookie → sha256 → join to user, expiry
  checked in SQL. Login failures are a generic 401 (no email enumeration).

## Data model (as-built)

- `users`: `id` UUID pk (client-generated uuid4), `email` varchar(255)
  unique, `password_hash` varchar(255), `created_at` timestamptz
  `server_default now()`.
- `sessions`: `id` UUID pk, `token_hash` char-64 unique, `user_id` FK →
  users **ON DELETE CASCADE**, `created_at`, `expires_at` timestamptz.
  Cascade is the model for all future user-owned tables.
- `interviews`: `id` UUID pk, `user_id` FK → users CASCADE, `status`
  enum (`preparing|ready|in_progress|judging|complete|abandoned`),
  `jd_text`, `resume_text`, `profile_json` JSONB,
  `session_type` enum (`screen|round|full_loop`, default `round`),
  `practice_tag` text nullable (set for skill drills instead of jd_text),
  `current_question_position` int nullable, `created_at`, `finished_at`.
- `questions`: `id` UUID pk, `interview_id` FK CASCADE, `position` int,
  unique `(interview_id, position)`, `qtype` enum, `text`, `answer_key_json`
  JSONB, `tags` TEXT[].
- `turns`: `id` UUID pk, `interview_id` + `question_id` FKs CASCADE,
  `role` enum (`interviewer|candidate`), `content`, `is_probe` bool,
  `created_at` (set explicitly on insert when multiple turns share a request).
- `evaluations`: `id` UUID pk, `interview_id` + `question_id` FKs CASCADE,
  `scores_json`, `evidence_json`, `missing_points_json` JSONB,
  `model_answer`, `judge_model`, `created_at`.
- `skill_scores`: `id` UUID pk, `user_id` FK → users CASCADE, `tag` text,
  `score_sum` float, `evaluation_count` int, `updated_at` timestamptz;
  unique `(user_id, tag)`. Running sum + count — average on read. Updated
  in `finish()` per judged answer (full overall score per tag).

## Interview flow (as-built)

- Backend-owned state machine in `app/interviews/state_machine.py` +
  `InterviewService`. Mock path runs intake + plan inline on create
  (`preparing→ready`), judge inline on finish (`judging→complete`).
- Per question: ASK → AWAIT_ANSWER → (PROBE → AWAIT_ANSWER)×≤2 → NEXT.
  Interviewer reply is advisory; backend enforces probe cap and index.
- Session types (named like real hiring stages): `screen` = 3 questions,
  `round` = 5 (default), `full_loop` = 7. Planner prompt mixes per count.
  Question count from plan only. (Replaced the old `dev_mode` bool —
  migration `d4e5f6a7b8c9` backfilled true→screen, false→full_loop.)

## Endpoints

- `GET /health` → `{status, env}` — liveness probe / smoke test.
- `POST /api/auth/register` → 201 UserOut + session cookie (auto-login);
  409 duplicate email; 422 invalid email / password < 8 chars.
- `POST /api/auth/login` → 200 UserOut + session cookie; 401 invalid.
- `POST /api/auth/logout` → 204, deletes session row, clears cookie
  (idempotent).
- `GET /api/me` → 200 UserOut; 401 without valid session.
- `DELETE /api/me` → 204, deletes user (sessions cascade), clears cookie.
- `POST /api/interviews` → 201 `{id, status: "ready"}` (mock) or 202
  `{id, status: "preparing"}` (deepseek, background intake+plan); body
  body has exactly one of `jd_text` / `practice_tag` (422 otherwise), plus
  `resume_text?`, `session_type?`. A `practice_tag` interview is a skill
  drill: intake parsing is skipped (profile stays null), the planner gets
  the tag + the user's current average (`generate_practice` on the
  PlanGenerator protocol), and every generated question carries the drilled
  tag (enforced server-side). Intake/plan failure → `abandoned`.
- `GET /api/interviews` → 200 `{interviews: [...]}` — the caller's
  interviews newest-first (cap 50, no pagination yet). Each summary:
  `{id, status, session_type, practice_tag, role, seniority, question_count, overall_score,
  created_at, finished_at}`; `role`/`seniority` null until intake parses,
  `overall_score` (mean of per-question score averages) null until judged.
  Rendered by the `/interviews` history page.
- `GET /api/interviews/{id}` → interview state (status, current question,
  turns, `awaiting_answer`); 404 if not owned.
- `POST /api/interviews/{id}/start` → `ready→in_progress`, presents Q1;
  409 on wrong status.
- `POST /api/interviews/{id}/answer` → body `{text}`; stores answer, may
  probe or advance; 409 if not awaiting answer.
- `POST /api/interviews/{id}/finish` → `in_progress→judging→complete`;
  409 if not all questions answered.
- `GET /api/interviews/{id}/report` → full report with answer keys; 409
  until `complete`.
- `GET /api/interviews/{id}/stream` → SSE (`text/event-stream`). Events:
  `question`, `token`, `interviewer_done`, `interview_complete`. Probes
  stream one `token` per LLM delta; planned questions chunk text. `InterviewEventBus` (in-process)
  bridges REST mutations to open streams; complete interviews replay
  `interview_complete` and close.
- `GET /api/methodology` → public (no auth): committed judge-eval artifacts
  from `backend/evals/results/*.json`, validated against `JudgeResults`,
  real judges sorted before the mock self-test. Rendered by the
  `/methodology` page (also public — the SPA router wraps both auth states).
- `GET /api/skills` → 200 `{skills: [{tag, average, evaluation_count,
  updated_at, trend}]}` sorted weakest-first; 401 without session. Populated
  when interviews finish. `trend` = latest-interview average minus the
  previous interview's on that tag (computed from evaluations); null until
  the tag is judged in two interviews.
- `GET /api/skills/{tag}` → 200 `{tag, average, evaluation_count, answers: [...]}` —
  every judged answer on the tag (question, candidate turns, scores, evidence,
  missing points, judge model, interview id/date), newest interview first.
  `{tag:path}` route because tags contain slashes; 404 when the user has no
  score for the tag. Answers predating skill tracking can appear without
  being counted in `evaluation_count` (dev-data artifact only).

## Run

```powershell
docker compose up -d postgres

# from backend/
uv sync
uv run alembic upgrade head               # apply migrations
uv run uvicorn app.main:app --reload      # http://127.0.0.1:8000
uv run pytest

# new migration after model changes
uv run alembic revision --autogenerate -m "describe change"

# from frontend/  (dev server proxies /api to the backend)
npm install
npm run dev                               # http://localhost:5173
npm run build                             # type-check + production build
```
