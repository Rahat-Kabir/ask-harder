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
| 7 | Skill tracking (aggregates, dashboard, planner reads weak tags) | **done** | Slices 1–3: aggregation, `/skills` UI, planner reads top 3 weak tags |
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

- 2026-06-12 — Skill tracking slice 1: `skill_scores` table (sum + count per
  user/tag, full score per tag on multi-tag questions), aggregation in
  `finish()` same transaction as evaluations, `GET /api/skills` (auth,
  weakest-first). Mock-judged and dev-mode interviews count — documented
  limitation.

- 2026-06-12 — Skill tracking slices 2–3: `/skills` dashboard (weakest-first
  bars, header nav, home teaser), `_prepare_interview()` loads top 3 weak
  tags into `skill_profile` for the planner.

- 2026-06-12 — UX polish (M8 slice): loading spinners, interview question
  progress, active nav, mobile header, focus rings, report overall score +
  skill link, intake preparing status line.

- 2026-06-12 — Visual pass: Instrument Serif + DM Sans, subtle background
  glow, page/card fade-in, staggered lists, skill-bar grow, button hover.
  Respects `prefers-reduced-motion`. Added streaming cursor on interviewer
  tokens and fixed film-grain overlay.

- 2026-06-12 — Real-pipeline browser run (DeepSeek v4 thinking + Sonnet judge,
  3-question dev mode, Playwright): both deferred verifications passed —
  no `[[DONE]]` leak in streamed chat, no placeholder variables in model
  answers. Probe logic worked as designed (two follow-ups on the weak
  Postgres answer, none on strong ones); Finish button appeared unprompted;
  report scores tracked answer quality (4.8 / 3.5 / 1.8); all evidence
  quotes verbatim; skills dashboard + home teaser populated weakest-first.
  New finding: Q1 model answer **fabricated a specific metric** ("latency …
  averages under 3 seconds per turn") not present in the answer or JD — the
  no-placeholder rule may push the judge to invent concrete numbers;
  consider a prompt rule against unverifiable stats.

- 2026-06-12 — Interview history slice: `GET /api/interviews` (newest-first
  summaries, cap 50; `overall_score` = mean of per-question score averages,
  null until judged; reuses `overall_score()` from skills) + `/interviews`
  history page (`HistoryPage.tsx`, "History" nav link). Row click by status:
  complete → report, ready/in_progress/judging → interview page,
  preparing/abandoned → not clickable. 3 new API tests (auth, ordering +
  scores, ownership isolation); verified clicking through to a real report
  in the browser. Also fixed pre-existing ruff failures in
  `tests/test_skills.py` and `src/app/skills/service.py` that were in CI
  scope. No pagination yet — documented limitation.

- 2026-06-12 — Skill drill-down ("the receipts"): `GET /api/skills/{tag:path}`
  (404 if the user has no score for the tag) returns every judged answer on
  the tag — question, candidate turns in order, scores, evidence, missing
  points, judge model, interview id/date — newest interview first. Frontend:
  skill bars on `/skills` are now links to `/skills/*` (splat route — tags
  contain slashes), new `SkillDetailPage` reuses report-card styling, links
  through to the full interview report; `formatTag` extracted to its own
  module (react-refresh lint). 5 new API tests (auth, 404, receipts content
  incl. probe replies, newest-first ordering, cross-user isolation); verified
  in the browser on the real dogfood data (deep link with slashed URL, error
  state, report link). Noted: evaluations that predate skill tracking show as
  receipts but aren't in `evaluation_count` — dev-data artifact only, the two
  are written in the same transaction going forward.

- 2026-06-12 — Profile page (frontend-only slice): `/profile` shows account
  info (email, member since), stats computed client-side from the existing
  `/api/interviews` + `/api/skills` endpoints (interviews taken/completed,
  overall average, judged answers, weakest/strongest skill), links to
  history/skills, and the first UI for `DELETE /api/me` (two-step inline
  confirm). Header email is now the link to `/profile` (was dead text);
  mobile truncates it instead of hiding it. Layout passes `{user, onLogout}`
  via router outlet context. Verified in the browser: rahat stats correct,
  fresh-account empty states, cancel resets the confirm, delete →
  auth page → re-login rejected. Quota display deferred with the quota
  feature itself.

- 2026-06-12 — Mobile audit (390×844, real browser + programmatic
  `scrollWidth` check on every page): all pages clean except report and
  skill detail, which overflowed 71px — unbreakable tokens (inline code in
  judge evidence/model answers) can't wrap. Fixed with one rule:
  `overflow-wrap: anywhere` on `blockquote`, `.report-block`,
  `.chat-bubble` (chat included — candidates can paste code/URLs).
  Re-verified both pages at 0px overflow. Noted, not built: sticky chat
  input on mobile; collapsible report question cards.

- 2026-06-12 — Session types (product reframe of interview length):
  `screen` (3 q, quick readiness check), `round` (5 q, default),
  `full_loop` (7 q, stress test) — named like real hiring stages, picked
  as cards on the intake page. Replaces `dev_mode` everywhere: enum column
  + migration `d4e5f6a7b8c9` (backfill true→screen, false→full_loop, drop
  bool), `question_count(session_type)`, planner prompt mix per count
  (5 = 1 warmup, 1 behavioral, 2 technical, 1 system_design), API in/out
  `session_type`, history/report show "Screen/Round/Full loop". 90 tests
  pass (+5: counts per type, default round, invalid 422). Browser-verified:
  default Round → "Question 1 of 5" → 5-question report "· Round",
  history row "· Round · 5 questions". No quota — deferred deliberately.

- 2026-06-12 — Trend view ("am I improving?", $0): `GET /api/skills` items
  gain `trend` — latest-interview average minus previous on that tag,
  computed from stored evaluations, null until 2 interviews. Dashboard rows
  show ▲/▼ delta; skill detail renders a hand-rolled SVG score-per-interview
  line (no chart library). 2 new API tests (null with one interview, exact
  delta across two). Browser-verified on dogfood data (ownership ▲ 2.8,
  chart 2.0 → 4.8).

- 2026-06-12 — Targeted practice ("drill my weakest skill"): `POST
  /api/interviews` takes exactly one of `jd_text` / `practice_tag` (422
  otherwise). Drills skip intake (profile null), plan via new
  `generate_practice(tag, average, n)` on the PlanGenerator protocol
  (mock re-tags its bank; DeepSeek gets a practice prompt that calibrates
  to the user's average; drilled tag enforced on every question
  server-side). `practice_tag` column + migration `e5f6a7b8c9d0`. "Drill
  this skill" button on skill detail (Screen-sized via shared `useDrill`
  hook); history/report show "Practice · <tag>". 2 new tests (validation,
  full drill lifecycle incl. skill aggregation). Browser-verified the
  flywheel: seed screen → drill from skill page → finish → drilled tag
  went 1 → 4 judged answers.

- 2026-06-12 — Report CTA (frontend-only, closes the loop): report ends
  with "What to work on next" — the lowest-scoring question's tag with
  [Drill it] (shared `useDrill`) and [See the receipts] (skill detail).
  Report → receipts → drill → trend is now one connected flywheel.
  Browser-verified on the real Sonnet report (picked the 1.8
  query-optimization question).

- 2026-06-12 — Quota + rate limiting (pre-launch hardening): daily
  interview quota (`DAILY_INTERVIEW_LIMIT=5`, UTC calendar day, abandoned
  refunded by exclusion) counted live from the interviews table — no
  counter to drift; 429 from `POST /interviews`, `GET /api/quota` feeds
  the intake counter (+ disabled submit at zero) and a profile cell.
  Auth rate limiting in `app/auth/rate_limit.py` (~40-line in-memory
  fixed-window limiter, injectable clock): 5 failed logins/email/5min
  (reset on success), 20 attempts/IP/5min, 5 registrations/IP/hour →
  429 + Retry-After; conftest clears limiters between tests. 11 new
  tests (4 limiter unit w/ fake clock, 3 auth endpoint, 4 quota incl.
  abandoned refund). Browser-verified: intake/profile counters, live
  6th failed login → 429 Retry-After 300.

- 2026-06-12 — Trust slice ($0): (1) pre-start confirmation — interview
  state now includes the parsed `profile`; the interview page no longer
  auto-starts on `ready` but shows "We read this JD as: <role · seniority>"
  with stack chips + competencies (drills show the tag) and an explicit
  Start button — a bad parse is caught before the user invests 30 minutes.
  (2) "How scoring works" legend on the report: the four dimensions
  explained + the grounding guarantees (verbatim quotes, frozen keys).
  2 new API tests (profile in state, null for practice); browser-verified
  both card variants, the start transition, and the legend.

- 2026-06-13 — Retake: `POST /api/interviews/{id}/retake` builds a fresh
  interview from the source's stored JD (or drilled tag), resume, and
  session type — quota applies. Report actions gain "Retake this
  interview" / "Drill this skill again". Pairs with the trend chart:
  attempt 1 → attempt 2 on the same role is now one click. 4 new tests
  (copies JD+session, copies practice tag, ownership, quota);
  browser-verified report → retake → confirmation card with same profile.

- 2026-06-13 — Saved resume: `users.resume_text` (migration
  `f6a7b8c9d0e1`), `PUT /api/me/resume` (blank clears), UserOut carries it.
  Profile gains a resume editor; intake auto-fills an untouched resume
  field from the saved value. 3 new auth tests; browser-verified save →
  prefill round trip.

- 2026-06-13 — Per-interview delete: `DELETE /api/interviews/{id}` is a
  **soft** delete (`deleted_at`, migration `a7b8c9d0e1f2`) — hidden from
  every user-facing query (single gate `_load_owned_interview` + list +
  skills joins) but still counted by the quota, closing the
  create→delete→create loophole. `recompute_skill_scores` rebuilds the
  affected tags from surviving evaluations so dashboard numbers keep
  matching the receipts. Report gains a quiet delete link with two-step
  confirm → navigates to history. 5 new tests (hidden everywhere,
  idempotent 404, ownership, quota retention, skill recompute + tag
  removal); browser-verified delete → empty history, recomputed skills,
  quota still 1 used.

- 2026-06-13 — Home daily briefing (frontend-only, replaces the static
  weakest-skills teaser): a "Today" card under the hero with quota left,
  last report score (links to it), weakest skill with trend arrow, and one
  suggested action — a dropping skill beats the merely-weakest one
  ("X dropped ▼0.5 — drill it") with an inline drill button (shared
  `useDrill`). Hidden until the user has interviews; hero unchanged for
  fresh accounts. Browser-verified on dogfood data.

- 2026-06-13 — Skip question (honest bail-out): `POST
  /api/interviews/{id}/skip` + `turns.is_skip` (migration `c9d0e1f2a3b4`).
  Skipping records "(skipped)", advances with no probe; fully-skipped
  questions get a deterministic floor evaluation (`judge_model="skipped"`,
  missing = full key, zero LLM calls) while a skipped *probe* after a real
  answer still uses the real judge. Floor scores feed skill tags. UI: Skip
  button beside Send, italic "You · skipped" bubble, "Skipped" badge on the
  report card. 4 new tests; browser-verified skip → advance → report badge
  → CTA picks the skipped tag.

- 2026-06-13 — Per-question timer (frontend-only, $0 — no schema change):
  soft time pressure. Live elapsed clock next to "Question x of y", started
  from the question's first turn timestamp (so a mid-question reload keeps
  honest time), reset on advance, stopped when all answered, probes count
  toward their question. Report cards show "answered in Xm Ys" computed
  from stored turn timestamps. No enforcement — the clock observes, the
  judge doesn't see it (yet). Browser-verified: backdated restore (0:41 on
  load), continuity across a probe, reset on advance, report durations
  matching reality.

- 2026-06-13 — UI polish pass (Playwright walk of every page, desktop +
  mobile): fixed score-grid cells — label/value collision on long values
  (gap + baseline alignment + right-aligned wrapping values); home
  briefing grid switched to full-width rows (its 560px card made
  half-width cells wrap to 3 lines). 0px horizontal overflow re-confirmed.
  Finding noted, not built: interviews that never reach `complete`
  (ready/in_progress) have no delete path in the UI — delete lives only
  on the report page.

- 2026-06-14 — The Verdict (the product's defining moment): the report now
  leads with a **pass / borderline / no** call for the role at its seniority,
  not just an average. Synthesized deterministically in
  `app/interviews/verdict.py` from the per-question scores already in the
  report — no LLM call, no stored column, no migration. Pass/borderline
  thresholds rise with seniority (junior 3.0/2.2 … senior 4.0/3.0 …
  staff/principal 4.3/3.3); drills and unknown seniority use the mid bar.
  Rationale is grounded — names the weakest question (by tag) and the
  weakest scoring dimension, and shows the bar vs. the achieved average so
  the call isn't a black box. `VerdictOut` on `ReportOut`; colored banner
  (green/amber/red) at the top of `ReportPage`. 8 new unit tests (bands per
  seniority, same scores pass at mid but fail at senior, borderline, drill
  skill-framing, weakest-question/dimension callout, empty, unknown
  seniority); 125 backend tests pass. Browser-verified: 3.3 mid → Borderline,
  2.7 senior → No (would've passed at mid — the seniority bar working).

- 2026-06-14 — Favicon + per-route tab titles (pre-ship polish): hand-rolled
  SVG favicon (`frontend/public/favicon.svg`) — a serif "a" in the accent
  orange on the dark surface, reusing the brand type/colors; linked in
  `index.html` (kills the favicon.ico 404). `TitleSync` in `App.tsx` sets
  `document.title` per route via `useLocation` ("History · ask-harder",
  "Report · ask-harder", etc.) so multiple open tabs are distinguishable;
  dynamic pages get a generic label. Browser-verified: titles change per
  route, favicon served 200 as image/svg+xml, no console 404.

- 2026-06-14 — Fix skipped-question model answer: replaced the raw
  `"; ".join(required_points)` string with `_skipped_model_answer()` — a
  module-level helper that produces Oxford-comma prose ("This question was
  skipped. A strong answer would cover: X, Y, and Z.") instead of a
  debug-looking semicolon list. 117 tests pass. Browser-verified on a
  fully-skipped Screen drill.

- 2026-06-14 — Delete non-complete interviews from History: `HistoryRow`
  gains a `×` button on every non-complete row (`preparing`, `ready`,
  `in_progress`, `judging`, `abandoned`). One click shows an inline
  "Delete? / Yes / Cancel" confirm; confirming calls the existing
  `DELETE /api/interviews/{id}` (soft delete) and removes the row from
  local state immediately. Complete interviews are unchanged — their
  delete action lives on the report page. Browser-verified: confirm
  flow, row disappears on "Yes", Cancel restores `×`, complete rows
  unaffected.

- 2026-06-16 — Scores presented out of 100 (product reframe — "out of 5"
  read like a failing academic grade; /100 is the familiar interview/exam
  frame). Design decision: keep the judge and all storage at 1–5 (the honest
  resolution an LLM can reproduce, and what the eval harness asserts on), and
  map to 0–100 only at the output boundary via `to_hundred` in
  `app/skills/service.py` — `25 × avg − 25` (1→0, 3→50, 5→100). The map is
  affine, so a stored running average converts directly and a trend scales
  ×25: **no DB migration, and pre-existing 1–5 data renders correctly**.
  Banding logic in `verdict.py` still runs on the 1–5 average; only its
  `bar`/`overall` outputs and rationale text are scaled (mid bar 62.5, senior
  75). Frontend: shared `scoring.ts` (`toHundred`/`overallOf`/`SCORE_MAX`),
  applied across Report/Skills/SkillDetail/Home/History/Profile; per-dimension
  chips deliberately stay 1–5; the skill-detail trend SVG y-axis rescaled to
  0–100. Equal dimension weighting kept (weighting correctness higher is a
  separate, deferred decision). 223 backend tests pass, frontend builds clean,
  Playwright-verified end-to-end: report "You scored 80/100, clearing the 75
  bar", skills/trend all on /100, skipped answers read 0/100.

- 2026-06-16 - Dogfood transcript audit for interview
  `53702a68-56af-44e0-95c7-79415bec6c1f`: DB showed a Round session with 5
  planned questions, 5 evaluations, and 18 turns. The apparent "9 questions"
  were 5 main questions plus 4 follow-up probes (two on Q1, two on Q3), so
  report/history correctly showed 5 planned questions. Fixed misleading
  interview-page copy from "may probe once" to "up to two follow-ups" to
  match the backend cap.

- 2026-06-16 - Report clarity slice after the same dogfood report: the strong
  model answer read like it might be the candidate's answer, especially next
  to 0/100 cards. Report cards now show "Your answer" from the stored
  candidate turns before evidence/missing points, and the old "Model answer"
  heading is renamed to "What a strong answer could include".

- 2026-06-16 - Report redesign (frontend-only, $0 — the page was one flat
  ~5000px stack of identical cards with no hierarchy or overview). Two slices:
  (1) **summary scorecard** under the verdict — large overall + `bar` "to pass"
  and the four dimensions as color-banded 0–100 bars (`dimensionAverages` in
  `scoring.ts`), so the shape of the interview reads at a glance; (2)
  per-question cards now **lead with score bars + "Missing from your answer"**
  and tuck *Your answer* / *Evidence* / *What a strong answer could include*
  behind `<details>` (cards default to calm, expand on demand). New `scoreBand`
  (red <50 / amber <75 / green ≥75) drives bar and per-question badge color.
  No schema/API change. Frontend builds clean; Playwright-verified across a
  pass report (80/100, green), a fail report (10/100, red/amber), the
  disclosure expand, and mobile 390px (scorecard stacks). Deliberately left
  unbuilt: the question overview / jump-list nav.

- 2026-06-16 - Dimension bars show a word, not a number (dogfood confusion fix):
  the per-dimension `/100` values (e.g. Correctness 15 above an overall of 10)
  read as a contradiction — two numbers in the same units that don't visibly
  reconcile. Replaced them with a word rating (`scoreLabel` in `scoring.ts`:
  Poor / Weak / Fair / Strong / Excellent, banded on the midpoints of the
  judge's native 1-5 buckets), colored to match the bar. The single `/100`
  overall is now the only number on the card, so nothing competes with it. The
  judge still scores 1-5 — deliberately *not* changed to score on 100 (an LLM
  can't reproduce 0-100 resolution; 1-5 is what the eval harness asserts on).
  Frontend-only. Playwright-verified: fail report reads Weak/Poor/Poor/Poor
  (red), pass report Strong (green) with Excellent per-question.

- 2026-06-16 - Intake expectation-setting copy (content fix — the session cards
  promised a flat "N questions", but the interviewer asks up to two follow-ups
  per question, so the count is contradicted in the live interview and the
  "Question 1 of N" counter looks stuck on a probe). Frontend-only copy:
  cards now say "N **core** questions", pitches name who each session is for
  ("A fast gut-check…" / "One realistic interview round — the default" / "The
  full gauntlet…"), and a note under the picker sets the follow-up expectation.
  Pre-start ready card mirrors "core questions". The in-interview probe label
  (`Interviewer · follow-up`) already existed, so it was left as-is.
  Playwright-verified the intake page.

- 2026-06-16 - Button-row alignment fix: `.primary-button` carried a
  `margin-top: 1rem` (intended for standalone hero CTAs) that pushed the orange
  button below the bordered buttons it shares a flex row with, so the report
  CTA (Drill it / See the receipts), the report footer actions, and the
  interview Send / Skip row looked misaligned. Neutralized the margin inside
  `.report-actions` / `.answer-actions` and added `align-items: center`.
  Playwright-verified the report CTA.

- 2026-06-16 - Site footer (content pages gave way to dead space at the bottom
  with no closure or home for secondary links). Slim global footer in `Layout`:
  brand voice line on the left, "How we test the judge" (→ /methodology),
  GitHub (github.com/Rahat-Kabir/ask-harder), and "Portfolio project · 2026"
  on the right. `margin-top: auto` in the flex-column shell pins it to the
  bottom on short pages. Deliberately **suppressed on the live interview
  workspace** (`/interviews/:id`, including the judging state) — a focused,
  full-height view where a footer competes with the answer box; intake
  (`/interviews/new`) and the report keep it. Playwright-verified footer
  present on home/intake/report and absent on the in-progress interview.

- 2026-06-16 - Account avatar + dropdown (the header showed a bare email, which
  reads as data, not "your account", and barely signals it's clickable). The
  email + standalone Log out button are replaced by an avatar circle (the
  email's first initial) that opens a dropdown with the full email, Profile,
  and Log out. `AccountMenu` in `Layout.tsx`: closes on outside-click, Escape
  (focus returns to the avatar), and route change; `aria-haspopup`/`aria-expanded`
  for a11y. Removed the now-dead `.session*` CSS. Playwright-verified open/close,
  outside-click, Escape, and Profile navigation; build clean.

- 2026-06-16 - Leak-free answer guidance (beginners couldn't tell what kind of
  answer a question wanted — short? long? what's needed to pass? — so a thin,
  unguessable answer risked measuring tool-confusion, not skill). Two changes,
  both deliberately *mechanics/format only*, never the rubric: (1) answer
  placeholder rewritten to "Answer as you'd say it out loud in a real interview
  — be specific and concrete. Vague answers score low." (register + specificity,
  no content leak); (2) the current question type (Warm-up / Behavioral /
  Technical / System design) now shows in the progress chip — a leak-free hint
  about the *shape* expected, sourced from `current_question.qtype` and the SSE
  `question` event. It stays unchanged through a follow-up probe (same question)
  and updates on advance. Explicitly **not** done: per-question content hints,
  required-point previews, or word-count targets — those would leak the frozen
  answer key, gut the report, and soften the "actually says no" identity.
  Verified $0 on a mock stack (uvicorn :8001 + vite :5176 via VITE_API_TARGET):
  chip showed "Question 1 of 5 · Warm-up", held through a probe, advanced to
  "Question 2 of 5 · Technical". Frontend builds clean.

- 2026-06-17 - Deployment prep, phase 1 (Docker for Heroku). Target stack:
  frontend → Vercel, backend → Heroku (container stack), DB → **Neon** (project
  `ask-harder`, London `aws-eu-west-2`, Postgres 17 — schema already migrated
  via `alembic upgrade head` with the `?ssl=require` + direct-host URL; no code
  change needed). Added `backend/Dockerfile` (python:3.13-slim + uv, two-stage
  sync for dep-layer caching), root `heroku.yml` (build from `backend/Dockerfile`
  with repo root as context; `release: alembic upgrade head`; `run: uvicorn`),
  and root `.dockerignore`. Decisions: (1) **container deploy over buildpack** —
  handles uv + the `backend/` subdir in one shot and makes local == prod; (2)
  app will use Neon's **direct (non-pooler) host** at this scale, so no
  PgBouncer/prepared-statement tuning and no `session.py` change — SSL rides in
  the `DATABASE_URL` (`?ssl=require`); (3) same-origin via a Vercel `/api`
  rewrite so the session cookie stays first-party (`SameSite=Lax`, no CORS).
  Not yet done: local Docker build/run verification, Heroku app config
  (`stack:set container`, config vars, GitHub auto-deploy), Vercel frontend.

- 2026-06-17 - Vercel frontend live + finish made async. Deployed the Vite SPA
  to Vercel as a single-app project (Root Directory `frontend`) with
  `frontend/vercel.json` rewriting `/api/*` → the Heroku backend (keeps the
  session cookie first-party, no CORS). Verified the whole stack end-to-end via
  Playwright at https://ask-harder.vercel.app — register/login, intake parse,
  SSE streaming interviewer, and the Sonnet-judged report all work through the
  proxy. **Bug found + fixed:** `POST /finish` judged every answer synchronously
  inside one request and tripped Heroku's 30s router timeout (H12 → 503), even
  though judging completed on the dyno. Reworked `finish()` to mark
  `judging`, commit, and judge out-of-band (mirrors the intake background-prepare
  pattern: `asyncio.create_task` + `new_session()`); the client polls interview
  state (`api.waitUntilJudged`) and also navigates on the existing
  `interview_complete` SSE event. Background failure reverts `judging→in_progress`
  so finish is retryable. Mock still judges inline (tests unchanged, 40 pass).
  Not yet done: redeploy backend (Heroku) + frontend (Vercel) with this fix;
  X-Forwarded-For handling so the rate limiter sees the real client IP behind
  the Vercel proxy.

## Known limitations

- FastAPI TestClient emits a Starlette deprecation warning about `httpx2`;
  revisit when bumping httpx.
- Expired session rows are never purged (harmless until scale).
- Rate-limit counters are in-memory per process — reset on restart, and
  per-IP keys only see the real client once X-Forwarded-For handling is
  added at deploy time.
- Quota check has a small race: concurrent creates at the boundary can
  exceed the daily limit by one.
- Skill averages mix mock and real judge scores on the same account until a
  `judge_model` filter is added later.

## Next up

- `run_comparison.py` (Batches API) and `/methodology` page (renders
  `evals/results/*.json`).
- Re-run all eval suites on Sonnet to verify the prompt/validator fixes.
