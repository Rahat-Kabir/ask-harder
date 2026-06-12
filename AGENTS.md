# ask-harder — Interview Copilot

AI mock interviewer for developers. Paste a JD → tailored interview → harsh,
evidence-grounded scored report. Portfolio project.

The *why* lives in [docs/VISION.md](docs/VISION.md) — read it to understand what the
product is trying to be. Product detail (stack, data model, API, LLM
contracts) lives in [docs/tech_spec.md](docs/tech_spec.md). New features are
decided in discussion with the user, slice by slice — there is no upfront
spec. This file grows step by step as the product is built — don't pre-write
rules for things that don't exist yet.

## Core Principles

- **Think Before Coding**: State assumptions. If uncertain, ask. Don't guess.
- **Simplicity First**: No overengineering. No "flexibility" that wasn't asked for.
- **Surgical Changes**: Only touch what is necessary. Don't reformat adjacent code.
- **Goal-Driven**: Create verifiable success criteria, then make them pass.
- **Fail Fast**: Don't swallow exceptions. Prefer a clear failure over silent
  fallback. Only catch with a specific recovery plan.
- **Ask Before Picking Tech**: Models, providers, libraries. Always confirm
  with the user before introducing a new one.

## Conventions

- **Names must carry meaning.** Variables, functions, and fields are named
  for what they hold or do — no cryptic abbreviations or one-letter names
  outside trivial loop indices.
- **Comment the non-obvious, not the obvious.** Where the code can't explain
  itself — a business rule, an invariant, a deliberate trade-off — add a
  short comment so the next dev or agent gets it without digging. Never
  comment what the code already says.
- Secrets in `.env` (gitignored), documented in `.env.example`.

## Global

- `AGENTS.md` is the source of truth. `CLAUDE.md` must stay byte-identical.
  Any edit to `AGENTS.md` must be mirrored to `CLAUDE.md` in the same change.
- After adding a new file, tool, or feature, update `README.md` and the
  Project Structure section in this file to reflect the change.
- After code changes, update `docs/PROGRESS.md` with what was built and the
  decisions made in the session. Read it before claiming "what's built" or
  "what's next."
- [`docs/tech_spec.md`](docs/tech_spec.md) is the as-built technical spec —
  update it when architecture, schema, or contracts change.
- [`docs/testing.md`](docs/testing.md) — update when test workflow or
  coverage changes.

## Project Structure

Only what exists is listed — update as milestones land; never pre-write
structure that doesn't exist yet.

```
ask-harder/
├── .github/workflows/ci.yml    # CI: ruff + pytest + mock evals + frontend build
├── AGENTS.md / CLAUDE.md        # this file + byte-identical mirror
├── README.md
├── LICENSE
├── docker-compose.yml           # postgres:17 only (dev DB)
├── .env.example                 # copy to .env locally (gitignored)
│
├── docs/
│   ├── VISION.md                # the why
│   ├── PROGRESS.md              # milestone status, decisions, next up
│   ├── tech_spec.md             # as-built technical spec
│   └── testing.md               # how to run tests
│
├── frontend/                    # Vite + React 19 + TypeScript
│   ├── vite.config.ts           # dev proxy: /api → 127.0.0.1:8000
│   └── src/
│       ├── main.tsx / App.tsx   # auth + react-router routes
│       ├── api.ts               # typed fetch wrapper for /api/*
│       ├── AuthPage.tsx         # login / register tabs
│       ├── Layout.tsx           # header shell (brand, logout)
│       ├── LoadingState.tsx       # shared spinner + label
│       ├── Home.tsx             # landing CTA + weakest-skills teaser
│       ├── SkillsPage.tsx       # skill dashboard (/skills)
│       ├── SkillDetailPage.tsx  # per-tag judged answers (/skills/*)
│       ├── ProfilePage.tsx      # account stats + delete account (/profile)
│       ├── formatTag.ts         # tag → display label helper
│       ├── useDrill.ts          # start a practice drill on one tag
│       ├── HistoryPage.tsx      # interview history list (/interviews)
│       ├── IntakePage.tsx       # JD paste → create interview
│       ├── InterviewPage.tsx    # SSE chat + answer/finish
│       ├── ReportPage.tsx       # scored report + answer keys
│       ├── MethodologyPage.tsx  # public eval results (no auth)
│       └── index.css
│
└── backend/                     # uv package `ask-harder-backend`
    ├── pyproject.toml
    ├── alembic.ini              # URL lives in env.py, not here
    ├── alembic/                 # migrations (async template)
    │   └── versions/
    ├── src/app/                 # import name `app`
    │   ├── main.py              # FastAPI app + /health, routers wired here
    │   ├── methodology.py       # GET /api/methodology — serves evals/results/
    │   ├── config.py            # pydantic-settings, reads root .env
    │   ├── schemas.py           # LLM I/O types (Profile, Plan, Evaluation, ...)
    │   ├── llm/
    │   │   ├── interfaces.py    # IntakeParser/PlanGenerator/Interviewer/Judge protocols
    │   │   ├── mock.py          # MockBackend (all four, deterministic, no API keys)
    │   │   ├── deepseek_common.py # v4 thinking/reasoning kwargs for DeepSeek calls
    │   │   ├── intake.py        # intake + plan generation (DeepSeek, JSON mode)
    │   │   ├── interviewer.py   # streaming interviewer (DeepSeek)
    │   │   ├── interviewer_common.py    # probe parse, text chunking
    │   │   ├── judge.py         # structured judge (Anthropic Sonnet)
    │   │   ├── judge_common.py          # evidence grounding validation
    │   │   ├── composite.py     # real intake/plan/interviewer/judge
    │   │   ├── factory.py       # LLM_BACKEND selection
    │   │   ├── prompts.py       # stable-prefix prompts
    │   │   └── errors.py        # IntakeParseError, LlmValidationError, ...
    │   ├── auth/
    │   │   ├── security.py      # argon2 hashing, session token gen/hash
    │   │   ├── schemas.py       # RegisterIn / LoginIn / UserOut
    │   │   ├── deps.py          # get_current_user (cookie → user)
    │   │   └── router.py        # /auth/*, /me endpoints
    │   ├── interviews/
    │   │   ├── state_machine.py # flow rules, probe cap, transition guards
    │   │   ├── schemas.py       # API I/O for interview endpoints
    │   │   ├── service.py       # InterviewService (DB + LLM backend via factory)
    │   │   ├── events.py        # in-process SSE fan-out bus
    │   │   ├── sse.py           # SSE line formatting
    │   │   └── router.py        # /interviews/* REST + /stream SSE
    │   ├── skills/
    │   │   ├── service.py       # finish-time aggregation, list, per-tag detail
    │   │   ├── schemas.py       # SkillOut / SkillsOut / SkillDetailOut
    │   │   └── router.py        # GET /api/skills, /api/skills/{tag}
    │   └── db/
    │       ├── base.py          # Base + constraint naming convention
    │       ├── models.py        # User, UserSession, Interview, Question, ...
    │       └── session.py       # async engine + get_session dependency
    ├── evals/                   # judge eval harness, no DB
    │   ├── conftest.py          # fixture loading, EVAL_JUDGE selection, results writer
    │   ├── test_judge.py        # 4 suites: ordering, stability, grounding, adherence
    │   ├── fixtures/            # 10 questions × {key, bad/mediocre/strong answers}
    │   └── results/             # per-judge metrics JSON (/methodology data source)
    └── tests/
        ├── conftest.py          # test DB bootstrap (askharder_test)
        ├── test_health.py
        ├── test_db_models.py
        ├── test_auth.py
        ├── test_llm_contracts.py
        ├── test_interviews.py
        ├── test_interview_stream.py
        ├── test_interview_sse_format.py
        ├── test_intake.py
        ├── test_methodology.py
        ├── test_skills.py
        ├── test_interviewer_common.py
        ├── test_judge_common.py
        ├── test_deepseek_common.py
        └── test_judge.py
```

## Collaboration

User prefers step-by-step development with discussion at each step. Before
large feature work:

- Explain the next small slice.
- Keep scope narrow.
- Build it.
- Verify it runs.
- Describe what changed and what was intentionally left unbuilt.

Response style: short and direct. No filler, no recap-summary at the end of
responses. State results and decisions; skip the narration.
