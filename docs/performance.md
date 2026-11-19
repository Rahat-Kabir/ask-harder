# Backend performance history

Use this benchmark to answer one question after a feature change: did a signed-in
user wait noticeably longer to open the same completed interview report?

## Compare before and after

Start the local Docker Postgres service and apply the checkout's migrations. From
`backend/`, run once **before** changing the feature and once **after** it. Choose
new filenames for each feature so earlier results stay available.

```powershell
$before = Join-Path $env:TEMP 'askharder-feature-before.json'
$after = Join-Path $env:TEMP 'askharder-feature-after.json'
uv run python scripts/benchmark_report.py --save $before
# Implement the feature, then repeat on the same machine and database.
uv run python scripts/benchmark_report.py --before $before --save $after
$LASTEXITCODE
```

The script starts its own loopback Uvicorn worker from the current checkout with
the mock backend. It creates a temporary account and a seven-question interview
through the API. Four questions receive an answer and a follow-up answer; three
are skipped. This gives 22 turns. The script validates the completed report,
compares each response with it, then deletes the temporary account and its data.
The workload exercises report reads; fixture creation and deletion are untimed.

Each of three batches runs one client followed by 12 simultaneous clients.
Each client warms its HTTP connection once, then times 30 full responses over
that connection. There are 1,170 timed reads. Median is the middle latency;
p95 uses the nearest rank. Keep machine load, Docker resources, database size,
and dependency versions comparable. The saved JSON includes the machine, OS,
Python version, database target, fixture fingerprint, Git revision, and dirty flag.

| Exit | Interpretation | Decision |
|---|---|---|
| 0 | Baseline captured, or compared runs stayed below the flag rule. | Record the result. |
| 1 | Runtime or correctness failure, such as a timeout, unexpected HTTP status, or incorrect report. | Investigate the error before using timings. |
| 2 | At the same client count, the same metric increased by **at least 25% and 20 ms** in at least two of three paired batches. | Investigate before shipping. |
| 3 | Only one batch crossed the threshold for a metric, or the recorded environment or workload differed. | Repeat under comparable conditions. If noisy results persist, record the uncertainty. |

## Local measurements

**2026-11-20 · initial baseline.** Windows 11, Python 3.13.3, local Docker
PostgreSQL 17.10, revision `2800891` with uncommitted changes, mock report
13,577 bytes. All 1,170 measured reads succeeded in each of the three runs.
Values below are milliseconds in batch order.

| Run | Clients | Median by batch | p95 by batch |
|---|---:|---|---|
| Baseline | 1 | 6.64 / 5.68 / 5.88 | 8.55 / 9.34 / 7.88 |
| Baseline | 12 | 44.18 / 45.36 / 42.60 | 138.75 / 59.88 / 163.20 |
| Same-code repeat | 1 | 5.70 / 5.70 / 5.66 | 7.68 / 6.56 / 6.47 |
| Same-code repeat | 12 | 41.35 / 41.61 / 41.21 | 170.85 / 96.87 / 104.72 |
| Second repeat | 1 | 5.68 / 5.76 / 5.93 | 6.95 / 6.66 / 7.41 |
| Second repeat | 12 | 40.83 / 38.65 / 45.81 | 60.20 / 102.62 / 126.11 |

Both repeats returned **inconclusive**. Each crossed both thresholds only in
the second 12-client p95 batch. The single-client results and concurrent medians
were more consistent. Append a dated comparison when evaluating a feature;
include the before/after revisions, success count, batch values, and decision.

## Production observations

| Date | Observation | Sample |
|---|---|---|
| 2026-11-20 | Idle Eco dyno took 16.74 s for the first health response; 16.16 s was router connect time. Warm health median was 162 ms from the client. | 1 idle request, 20 warm |
| 2026-11-20 | Three-question screen took 14.42 s to become ready and 54.08 s from finish to observed completion. Signed-in report reads took 242 ms median. | 1 paid synthetic interview, 12 report reads |

These measurements preserve the observed production waits. The local regression
rule applies to its fixed mock workload only.
