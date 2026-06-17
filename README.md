# ask-harder

[![CI](https://github.com/Rahat-Kabir/ask-harder/actions/workflows/ci.yml/badge.svg)](https://github.com/Rahat-Kabir/ask-harder/actions/workflows/ci.yml)

AI mock interviewer for developers — paste a job description, take a tailored
interview, get harsh, evidence-grounded feedback. _"The interviewer that
actually says no."_

## Why this exists

Most AI interview tools are friendly chatbots: they ask generic questions,
then tell you that you did great. Feedback you can't trust is worthless —
especially the positive kind. ask-harder is built on the opposite premise: a
verdict is only useful if you can trust the "no". So every score must point
at words you actually said, every reported gap must come from a pre-defined
rubric, and the judging model itself is tested like code, with the test
results published.

## How it works

```
job description ──► profile ──► question plan (hidden answer keys)
                                      │
                            streaming chat interview
                            (follow-up probes, capped)
                                      │
                           judge grades each answer
                           against its frozen key
                                      │
                    report: scores · verbatim evidence ·
                    missing points · model answers
```

1. **Intake** — paste a JD (and optionally a resume); an LLM extracts a
   structured profile: role, seniority, stack, competencies.
2. **Plan** — questions are generated for that profile (warmup, behavioral,
   technical, system design). Each question carries an **answer key**
   (required points, strong signals, red flags), frozen before the interview
   starts.
3. **Interview** — a streaming chat (SSE). The interviewer can ask follow-up
   probes; the backend enforces the probe cap, not the model.
4. **Judge** — after you finish, each answer is scored 1–5 on correctness,
   depth, structure, and communication — strictly against the frozen key.
5. **Report** — a top-line **verdict** (pass / borderline / no for the role
   at its seniority, with a rationale grounded in your weakest answer and
   dimension) and an **overall out of 100** (the four 1–5 dimensions mapped
   onto 0–100), then per-question scores, evidence quotes, what you failed to
   mention, and a model answer per question. Answer keys are revealed only here.

Two trust guarantees are enforced in code, not in prompts:

- **The interviewer can never see answer keys.** Its interface receives a
  question type that has no key field — leaking a key into an interview
  prompt is a type error, not a code-review hope.
- **Judge output is post-validated.** Every evidence quote must be a
  verbatim substring of the transcript; every missing point must be an
  actual answer-key string. Anything else is retried, then stripped.

## The judge is tested, not trusted

LLM judges fail in predictable ways: fabricated quotes, invented criteria,
scores that drift between runs. `backend/evals/` is a fixed benchmark that
measures this: 10 questions across all four types, each with bad, mediocre,
and strong answers of _known_ quality, run against the judge's raw output
and asserted on four properties — **ordering** (bad < mediocre < strong),
**stability** (≤ ±0.5 score spread across runs), **grounding** (every quote
verbatim), and **key adherence** (reported gaps are real key strings).

It has already paid for itself: the first real run caught the judge splicing
quotes with ellipses and paraphrasing key points — both fixed in the prompt
and validator. Each eval run writes its metrics as JSON to
`backend/evals/results/`.

## Stack

FastAPI · Python 3.13 · PostgreSQL 17 · SQLAlchemy 2 (async) · Alembic ·
React 19 + TypeScript + Vite · DeepSeek (intake / plan / interviewer) ·
Claude Sonnet (judge) · pytest

## Run it locally

Requires: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```powershell
# 1. configure env
copy .env.example .env   # then edit values

# 2. database
docker compose up -d postgres

# 3. backend (from backend/)
uv sync
uv run alembic upgrade head            # apply DB migrations
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000/health

# 4. frontend (from frontend/) — proxies /api to the backend
npm install
npm run dev                            # http://localhost:5173
```

Then open http://localhost:5173 — register, paste a job description, pick a
session size (Screen · 3, Round · 5, or Full loop · 7 questions), answer the
questions, finish, read your report. Visit `/skills`
to see skill averages after finishing at least one interview — click any
skill to see every judged answer behind its score — and `/interviews` for
the history of every interview you've taken. Your email in the header opens
`/profile`: account stats at a glance and account deletion.

**Explore the database** (interactive `psql` shell; requires Postgres running):

```powershell
docker exec -it askharder-postgres-1 psql -U askharder -d askharder
```

Inside `psql`: `\dt` lists tables, `SELECT COUNT(*) FROM users;` counts
accounts, `\q` quits.

**LLM modes** (`LLM_BACKEND` in `.env`):

- `mock` (default) — deterministic fake LLM, no API keys, full flow works.
- `deepseek` — real models; set `DEEPSEEK_API_KEY` and `ANTHROPIC_API_KEY`.

When using `deepseek`, model ids and v4 thinking mode are env-configurable per role:

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_INTAKE_MODEL` | Intake parser model |
| `DEEPSEEK_PLAN_MODEL` | Question planner model |
| `DEEPSEEK_INTERVIEWER_MODEL` | Streaming interviewer model |
| `DEEPSEEK_THINKING` | `enabled` or `disabled` — global for all DeepSeek roles |
| `DEEPSEEK_REASONING_EFFORT` | `high` or `max` — when thinking is enabled |
| `ANTHROPIC_JUDGE_MODEL` | Judge model (any Anthropic model id) |

See [`.env.example`](.env.example) for defaults and v4 examples.

```powershell
# tests (from backend/)
uv run pytest tests

# judge evals (from backend/) — mock judge needs no API keys
uv run pytest evals
# real judge: $env:EVAL_JUDGE='anthropic'; uv run pytest evals
```

## Develop a feature (local → prod)

Local and production are fully isolated: local reads `.env` (local Postgres,
`LLM_BACKEND=mock`); production reads its `DATABASE_URL` and API keys from
Heroku config vars. Nothing you run locally touches Neon or live data.

```powershell
git switch -c feat/my-thing           # main stays always-deployable

# backend (terminal 1, from backend/) + frontend (terminal 2, from frontend/)
uv run uvicorn app.main:app --reload  # http://127.0.0.1:8000
npm run dev                           # http://localhost:5173 — proxies /api to the backend
```

Build against `LLM_BACKEND=mock` (instant, free, deterministic, exercises the
whole flow); switch to `deepseek` only when the change affects real LLM
behavior. If the feature changes the schema, generate a migration — it applies
to prod automatically on the next Heroku release:

```powershell
uv run alembic revision --autogenerate -m "describe change"   # after editing db/models.py
uv run alembic upgrade head                                   # apply locally and test
```

Before shipping, run the same gates CI enforces (`.github/workflows/ci.yml`),
then deploy:

```powershell
# backend — ruff lint + format check, then tests and the eval harness
cd backend
uv run ruff check src tests evals
uv run ruff format --check src tests evals
uv run pytest tests
uv run pytest evals

# frontend — eslint (not run by `build`) + the type-checked build
cd ../frontend
npm run lint
npm run build

git push origin feat/my-thing         # open a PR, or merge to main when ready
# merging to main → Vercel auto-deploys the frontend
git push heroku main                  # backend; release runs `alembic upgrade head`
```

## Repository layout

```
ask-harder/
├── docker-compose.yml        # dev database (postgres:17)
├── heroku.yml                # Heroku container deploy (release runs migrations)
├── docs/                     # vision, as-built tech spec, testing, progress log
├── frontend/                 # React 19 + TypeScript SPA (Vite, /api proxy)
│   └── src/                  # pages: auth, JD intake, SSE chat, report
└── backend/                  # FastAPI app (uv package, src layout)
    ├── Dockerfile            # backend image + .dockerignore (Heroku; context=backend/)
    ├── src/app/
    │   ├── llm/              # the four LLM components + mock backend
    │   ├── auth/             # sessions, argon2, /auth + /me endpoints
    │   ├── interviews/       # state machine, service, REST + SSE
    │   └── db/               # SQLAlchemy models, async session
    ├── alembic/              # schema migrations
    ├── evals/                # judge benchmark: fixtures, suites, results
    └── tests/                # pytest against a real Postgres test DB
```

Architecture, data model, and API reference: [docs/tech_spec.md](docs/tech_spec.md).

## Deployment

Target stack: **frontend on Vercel**, **backend on Heroku** (container stack,
built from [`backend/Dockerfile`](backend/Dockerfile) via
[`heroku.yml`](heroku.yml) — the release phase runs `alembic upgrade head`),
and **PostgreSQL on Neon**. The backend's `DATABASE_URL` uses the
`postgresql+asyncpg://…?ssl=require` form (asyncpg, not libpq `sslmode`).
Secrets live only as platform config vars, never in the repo.

## License

[MIT](LICENSE)
