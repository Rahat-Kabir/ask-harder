# Testing

Backend tests live in `backend/tests/`, run with pytest:

```powershell
# postgres must be running (docker compose up -d postgres)
# from backend/
uv run pytest
```

## How DB tests work

- Tests run against a real Postgres database, `askharder_test` — same
  container as dev, separate database. The dev DB is never touched.
- `tests/conftest.py` rewrites `DATABASE_URL` **before any app import**
  (env vars beat the `.env` file in pydantic-settings), creates
  `askharder_test` if missing, and runs `alembic upgrade head` once per
  session — tests always run against the migrated schema, not `create_all`.
- After each test the `client` fixture truncates all tables (isolation) and
  disposes the engine pool (anyio gives each test a fresh event loop;
  pooled asyncpg connections are bound to the old one).
- HTTP calls go through httpx `AsyncClient` + `ASGITransport` — the real
  ASGI app, no network, cookies handled like a browser.

## Layers

- `test_health.py` — app boots, liveness.
- `test_db_models.py` — schema shape (no DB).
- `test_auth.py` — full auth flows against the test DB, including the
  argon2-hash-at-rest check and the `DELETE /me` cascade verified in-DB.
- `test_interviews.py` — mock interview lifecycle (create → start → answer
  all questions with probe → finish → report), ownership, invalid
  transitions, `DELETE /me` cascades interviews.
- `test_interview_stream.py` / `test_interview_sse_format.py` — SSE event
  bus contract, wire format, HTTP replay for complete interviews.
- `test_intake.py` — intake/plan JSON parsing (DeepSeek classes, mocked
  HTTP); tests force `LLM_BACKEND=mock` via conftest.
- `test_judge.py` — AnthropicJudge grounding retry/strip pipeline (mocked
  Anthropic client).

## Eval harness (`backend/evals/`)

Judge quality evals — separate from the unit/integration suite,
no database needed:

```powershell
# from backend/
uv run pytest evals                            # mock judge, no API keys — plumbing check
$env:EVAL_JUDGE='anthropic'; uv run pytest evals   # real Sonnet judge (~30 paid calls)
```

- `evals/fixtures/` — 10 questions across all 4 qtypes, each with an answer
  key and bad/mediocre/strong candidate answers.
- `evals/test_judge.py` — four suites: 1 (ordering: overall
  score bad < mediocre < strong per fixture), 2 (stability: per-dimension
  spread ≤ ±0.5 across 3 runs — marked `stability`, 60 extra real-model
  calls; deselect with `-m "not stability"`), 3 (grounding: every evidence
  quote verbatim in the transcript), 4 (key adherence: ≥80% of
  `missing_points` are actual answer-key strings), plus non-triviality
  guards (strong answers yield evidence, bad answers have missing points).
- Evals assert on the judge's **raw** model output (`evaluate_raw`) — the
  production `evaluate()` strips ungrounded evidence and filters
  `missing_points`, which would make these assertions pass by construction.
- Judge results are cached per (fixture, answer, run) for the session —
  suites 1/3/4 share run 0 (30 model calls); stability adds runs 1–2
  (60 more).
- Every session writes its metrics to `evals/results/<judge>.json`
  (grounding rate, key adherence, per-fixture scores/ordering/spread) —
  the committed artifact the `/methodology` page will render.
- The model comparison (`run_comparison.py`) is not built yet.

## IDE setup

If Pyright reports false "import could not be resolved" warnings, set the
Python interpreter to `backend/.venv` in VS Code/Cursor.
