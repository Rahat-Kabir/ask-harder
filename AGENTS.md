# ask-harder — Agent Instructions

## Overview

AI mock interviewer for developers: paste a JD → tailored interview → harsh,
evidence-grounded scored report. Portfolio project, live at
https://ask-harder.vercel.app (Vercel frontend + Heroku backend + Neon
Postgres). Built slice by slice in discussion with the user — there is no
upfront spec; never pre-write rules or structure for things that don't exist
yet. `CLAUDE.md` is an `@AGENTS.md` import pointer — edit this file, never
CLAUDE.md.

## Docs

- `docs/VISION.md` — the why. Every feature must serve it; question anything that doesn't.
- `docs/PROGRESS.md` — session log. Update after product changes — features,
  fixes, architecture, decisions; skip meta and docs-only edits. Keep entries
  short. Read before claiming what's built or what's next.
- `docs/tech_spec.md` — as-built spec. Update when architecture, schema, or contracts change.
- `docs/testing.md` — verification workflow. Update when it changes.
- `docs/eval_results.md` — real-judge eval sessions: results, decisions,
  caveats. Append a section per paid run.
- `README.md` — update when setup, commands, or user-visible features change.
- Doc style: clarity first — add words when understanding needs them;
  otherwise fewest words that carry the meaning.

## Architecture

- Monorepo: `backend/` (FastAPI, uv package, import name `app`) +
  `frontend/` (Vite + React 19 + TypeScript). All frontend-facing API routes
  live under `/api` (`/health` stays unprefixed for infrastructure probes);
  SPA and API share one origin (Vite dev proxy locally, Vercel rewrite in
  prod) so the session cookie stays first-party — no CORS.
- Postgres 17 (docker compose in dev, Neon in prod), SQLAlchemy 2.0 async +
  Alembic migrations. API schemas are separate Pydantic models, never ORM
  models over the wire.
- Auth: argon2 hashing, DB-backed sessions (sha256 of the cookie token at
  rest, never the token), HTTP-only cookies, in-memory rate limiting.
- LLM pipeline: four components — intake parser, plan generator, interviewer,
  judge — as Protocols (`app/llm/interfaces.py`) with typed I/O in
  `app/schemas.py`. Real stack: DeepSeek (intake/plan/interviewer, streaming)
  + Anthropic Sonnet (judge). `LLM_BACKEND=mock|deepseek` via factory.
- Interview flow: state machine with probe cap, SSE streaming over an
  in-process event bus, deterministic verdict computed at report time.
- Judge quality has its own eval harness (`backend/evals/`, no DB) whose
  results JSON feeds the public `/methodology` page.

### Key Decisions

- **Context starvation at the type level** — the Interviewer receives
  `InterviewQuestion` (no answer key); only the Judge sees `PlannedQuestion`
  (with key). Answer-key leakage is impossible by construction, not by prompt.
- **MockBackend implements all four LLM protocols deterministically** —
  tests, CI, and offline dev run with zero API keys and zero paid calls.
- **Real-backend judging and intake run out-of-band** (`asyncio.create_task` + fresh DB
  session) — Heroku's router kills requests at 30s (H12), and synchronous
  judging inside `finish()` tripped it in prod. `finish()` marks `judging`,
  commits, returns; the client polls state and listens for the SSE complete
  event. Background failure reverts `judging → in_progress` so finish is
  retryable. Mock still judges inline, so tests are unchanged.
- **The verdict is deterministic Python, not an LLM call**
  (`interviews/verdict.py`) — pass/borderline/no banded by seniority,
  synthesized from stored per-question scores. Reproducible, free, no
  stored column.
- **Scores are judged and stored 1–5; /100 exists only at the output
  boundary** (`to_hundred`, affine `25×avg−25`) — 1–5 is the resolution an
  LLM can actually reproduce and what the evals assert on; the affine map
  means stored averages and trends convert directly, no migration.
- **Judge output is post-validated** — evidence quotes must appear verbatim
  in the transcript (retry once, then strip); `missing_points` filtered
  char-for-char to answer-key strings. Evals assert on the *raw* judge
  output — asserting on production output would pass by construction.
- **Interview delete is soft** (`deleted_at`) and still counts toward the
  daily quota — closes the create→delete→create quota loophole.
- **The judge runs at `effort: "medium"`, not high** — validated 2026-07-17
  by the eval harness (ordering 10/10, grounding and adherence 100%,
  stability within ±0.5); high effort was decorative for this rubric-bound
  task. Any effort or judge-model change needs a fresh eval run first —
  see `docs/eval_results.md`.

## Key Files

| File | ~Lines | Purpose |
|---|---|---|
| `backend/src/app/interviews/service.py` | 1000 | Orchestration core: lifecycle, DB, LLM calls, background judging |
| `backend/src/app/interviews/state_machine.py` | 65 | Flow rules, probe cap (2), transition guards |
| `backend/src/app/interviews/verdict.py` | 250 | Deterministic verdict and recovery priorities, seniority-banded |
| `backend/src/app/schemas.py` | 115 | Typed LLM I/O contracts (Profile, Plan, Evaluation, …) |
| `backend/src/app/llm/prompts.py` | 135 | All prompts, stable-prefix for caching — ruff E501-exempt |
| `backend/src/app/llm/mock.py` | 210 | Deterministic mock of all four LLM protocols |
| `backend/src/app/llm/judge.py` + `judge_common.py` | 100+70 | Sonnet judge + evidence-grounding validation |
| `backend/src/app/skills/service.py` | 310 | Finish-time skill aggregation, trend, `to_hundred` |
| `backend/src/app/db/models.py` | 200 | All tables (User, Interview, Question, Turn, …) |
| `backend/evals/conftest.py` | 210 | Eval harness: fixture loading, judge selection, results writer |
| `frontend/src/api.ts` | 335 | Typed fetch wrapper for `/api/*` |
| `frontend/src/InterviewPage.tsx` | 565 | SSE chat, answer/skip/finish, judging poll |
| `frontend/src/ReportPage.tsx` | 525 | Verdict banner, recovery plan, scorecard, rubric checklist, drill CTA |
| `frontend/src/scoring.ts` | 60 | 1–5 → /100 mapping, bands, labels — mirrors backend scaling |

## Commands

```bash
# dev DB (repo root)
docker compose up -d postgres

# backend (from backend/)
uv run uvicorn app.main:app --reload    # dev server :8000
uv run pytest tests                     # needs postgres; runs against askharder_test DB
uv run ruff check src tests evals       # lint (--fix for autofixes)
uv run ruff format src tests evals
uv run alembic upgrade head             # after editing db/models.py: revision --autogenerate first

# evals (from backend/)
uv run pytest evals                     # mock judge — free, this is what CI runs
# EVAL_JUDGE=anthropic switches to the real Sonnet judge: ~30 PAID calls,
# +60 more with the stability suite (deselect: -m "not stability").
# Never run the real judge without asking.

# frontend (from frontend/)
npm run dev                             # :5173, proxies /api → :8000
npm run lint                            # eslint — build does NOT run it
npm run build                           # type-checked build (CI gate)
```

## Conventions

- LLM modules are role-named (`intake.py`, `interviewer.py`, `judge.py`);
  provider-specific logic lives in provider-named classes.
- Tables and migrations are added with the feature that needs them, never upfront.
- Secrets live in the root `.env` (gitignored); `.env.example` documents them
  with placeholders only.

## Definition of Done

A slice is done when the CI gates pass locally — `ruff check` +
`ruff format --check`, `pytest tests`, `pytest evals` (mock), frontend
`lint` + `build` — and user-facing changes are verified in a real browser
(Playwright or manual), not only through tests. Then update docs per the
Docs section.

## Engineering Principles

- No overengineering, no "flexibility" that wasn't asked for.
- Readability over simplicity: when the two conflict, the readable version wins.
- Surgical changes: touch only what's necessary; don't reformat adjacent code.
- Goal-driven: define verifiable success criteria, then make them pass.
- Fail fast: don't swallow exceptions; only catch with a specific recovery plan.
- Clean up orphans: removing code means removing its unused imports, tests,
  and dependencies too.

## Code Style

### Naming

IMPORTANT: follow these naming rules strictly. Clarity is the top priority.

- Be as clear and specific with variable and method names as possible.
- Optimize for clarity over concision. A developer with zero context on the
  codebase should immediately understand what a variable or method does just
  from reading its name.
- Use longer names when it improves clarity. Do NOT use single-character
  variable names.
- Follow the language's casing convention: `snake_case` in Python,
  `camelCase` in JavaScript/TypeScript.
- Example: use `original_question_last_answered_date` (Python) or
  `originalQuestionLastAnsweredDate` (JS/TS) instead of `original_answered`.
- When passing props or arguments to functions, keep the same names as the
  original variable. Do not shorten or abbreviate parameter names. If you have
  `currentCardData`, pass it as `currentCardData`, not `card` or `cardData`.

### Code Clarity

- Clear is better than clever. Do not write functionality in fewer lines if it
  makes the code harder to understand.
- Write more lines of code if additional lines improve readability and
  comprehension.
- Make things so clear that someone with zero context would completely
  understand the variable names, method names, what things do, and why they exist.
- When a variable or method name alone cannot fully explain something, add a
  comment explaining what is happening and why — in code you write or change.

## Do NOT

- Do not add features, refactor code, or make "improvements" beyond what was asked.
- Do not add docstrings, comments, or type annotations to code you did not change.
- Do not introduce new tech — library, framework, model, or provider —
  without asking first.
- Do not rewrap or reformat text in `app/llm/prompts.py` (deliberately
  E501-exempt) — rewrapping the strings changes the prompts.
- Do not "fix" the Starlette/httpx deprecation warning in tests — known,
  revisit when bumping httpx.
- Do not run paid LLM calls (real-judge evals, live DeepSeek/Anthropic runs)
  without asking first.

## Git Workflow

- Branch naming: `feature/description` or `fix/description`.
- The user normally works directly on `main`; use a feature or fix branch only when requested.
- Commit messages: Conventional Commits (`feat:`, `fix:`, `docs:`, …),
  imperative mood, concise, explain the "why" not the "what".
- Do not force-push to main.

## Self-Update

When you make changes to this project that affect the information in this
file, update this file to reflect those changes. Specifically:

- **New files**: add notable new source files to the Key Files table with
  their purpose and approximate line count.
- **Deleted files**: remove entries for files that no longer exist.
- **Architecture changes**: update the Architecture section if you introduce
  new patterns, frameworks, or significant structural changes.
- **Build changes**: update the Commands section if the build process changes.
- **New conventions**: if the user establishes a new coding convention during
  a session, add it to the appropriate conventions section.
- **Line count drift**: if a file's line count changes significantly
  (>50 lines), update the approximate count in the Key Files table.
- **Empty slots**: when something a slot describes first comes into existence
  (a verification workflow, a new `docs/` file), fill that slot and delete its
  guidance comment.

Do NOT update this file for minor edits, bug fixes, or changes that don't
affect the documented architecture or conventions.
