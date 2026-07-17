# Judge Eval Results

Findings from real-judge eval sessions. One section per session, newest
first. The committed metrics artifact lives at
`backend/evals/results/<judge>.json` and feeds the public `/methodology`
page; this file records the *decisions and lessons* around those numbers.

## 2026-07-17 — First full run: Sonnet 4.6 at effort medium

**The decision under test.** The judge had always run with adaptive thinking
at `effort: "high"` — chosen by default, never by evidence. Since the judge
task is deliberately mechanical (frozen rubric, verbatim quoting, code-side
validators), we hypothesized `medium` would pass the same bars at lower cost
and latency. We switched production to medium (one line in
`app/llm/judge.py`) and evaluated *that*, because evals must test the judge
we ship.

**Result: medium passed everything.** 92/92 tests, 90 evaluations
(10 fixtures × 3 answer qualities × 3 stability runs):

| Suite | Bar | Result |
|---|---|---|
| Ordering | bad < mediocre < strong per fixture | 10/10, correct in all three runs |
| Grounding | every evidence quote verbatim | 341/341 (100%) |
| Key adherence | missing points are exact key strings | 196/196 (100%) |
| Stability | per-dimension spread ≤ ±0.5 across 3 runs | passed; worst case one dimension flipping a single point, never over the bar |

This also confirms the June prompt/validator fixes: the first-ever Sonnet
run (June, old prompt, 43/52) failed on ellipsis-spliced quotes and 71% key
adherence. Both are now clean.

**Standing decision: the judge runs at `effort: "medium"`.** High effort
was decorative for this task. Revisit only with a fresh eval run — the
harness is the referee for any effort/model change.

### Cost actuals

- Input tokens were measured before spending anything, via the free
  `count_tokens` endpoint: avg 694/call + ~389 schema overhead.
- Stage 1 (30 calls, no stability): ~$0.50.
- Stage 2 (90 calls, full suite): ~$1.50, 17m48s wall clock.
- Whole session including the earlier partial run: ~$2.

### Harness bug found and fixed

The harness built a fresh `AnthropicJudge` per call and never closed its
HTTP client. On Windows, garbage collection later closed those clients on
dead event loops, and anyio surfaced the `Event loop is closed` errors into
whichever *innocent* test was running — Stage 1 showed 6 "failures" of
which only 1 was real. Fix: `AnthropicJudge.aclose()` + a `try/finally` in
`evals/conftest.py` closing each judge on its own loop. Stage 2 ran clean.

### Caveats to keep honest

- **Fixtures are AI-authored.** All 30 answers were written by an agent,
  then human-reviewed (2026-07-17): every bad/mediocre/strong label was
  endorsed, so ordering ground truth stands. But:
- **Bad answers are tidily bad** — each states its fixture's red flag
  almost verbatim. Real candidates are bad by being vague, not by
  confidently asserting the forbidden sentence. The judge's exam is easier
  than production.
- **The top of the scale is untested.** Every strong answer scored a
  perfect 5.0 in all runs — the synthetic strong answers are essay-perfect,
  so we've never observed the judge grade a realistic "good but human"
  answer. Real dogfood transcripts would make better future fixtures.
- One ungrounded quote (1/112) appeared in the Stage 1 session and never
  recurred across 341 quotes in Stage 2 — treated as rare LLM flake, and
  production strips such quotes anyway. The results JSON records counts but
  not offending quotes; logging them is a possible harness improvement.

### Still open for M6

`run_comparison.py` (second judge model compared on the same fixtures) was
never built. Candidates: Haiku 4.5 (zero new code — same `AnthropicJudge`,
different model id; results file naming must stop keying by backend first)
or a DeepSeek judge class. Decision pending.
