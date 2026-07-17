import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type FixtureResults, type JudgeResults } from './api'
import { LoadingState } from './LoadingState'

const SUITES = [
  {
    name: 'Ordering',
    claim:
      'Graded on the same question, a bad answer must score below a mediocre one, and mediocre below strong — for every fixture.',
  },
  {
    name: 'Stability',
    claim:
      'Judging the same answer three times may not move any score dimension by more than ±0.5.',
  },
  {
    name: 'Grounding',
    claim:
      'Every evidence quote the judge cites must appear verbatim in the candidate’s answer — no fabricated quotes.',
  },
  {
    name: 'Key adherence',
    claim:
      'Every gap the judge reports must be an actual answer-key criterion, not an invented one.',
  },
]

const ANSWER_QUALITIES = ['bad', 'mediocre', 'strong'] as const

// the stability suite's bar: ±0.5 on any dimension, i.e. max − min ≤ 1
// on the integer 1-5 scale
const MAX_STABLE_SPREAD = 1

function percent(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`
}

function orderingSummary(fixtures: JudgeResults['fixtures']): string {
  const checked = Object.values(fixtures).filter(
    (fixture) => fixture.ordering_ok !== undefined,
  )
  if (checked.length === 0) return '—'
  const ok = checked.filter((fixture) => fixture.ordering_ok).length
  return `${ok}/${checked.length} fixtures`
}

function stabilitySummary(fixtures: JudgeResults['fixtures']): string {
  let stableAnswers = 0
  let checkedAnswers = 0
  for (const fixture of Object.values(fixtures)) {
    for (const quality of ANSWER_QUALITIES) {
      const spread = fixture[quality]?.spread
      if (!spread) continue // spread exists only when repeat runs happened
      checkedAnswers += 1
      if (Object.values(spread).every((value) => value <= MAX_STABLE_SPREAD)) {
        stableAnswers += 1
      }
    }
  }
  if (checkedAnswers === 0) return 'not run'
  return `${stableAnswers}/${checkedAnswers} within ±0.5`
}

function answerSetCount(fixtures: JudgeResults['fixtures']): number {
  let count = 0
  for (const fixture of Object.values(fixtures)) {
    for (const quality of ANSWER_QUALITIES) {
      if (fixture[quality]) count += 1
    }
  }
  return count
}

function firstRunOverall(
  fixture: FixtureResults,
  quality: (typeof ANSWER_QUALITIES)[number],
): string {
  const overall = fixture[quality]?.overall_by_run['0']
  return overall === undefined ? '—' : overall.toFixed(2)
}

// "q03_rate_limiter" → "rate limiter"
function fixtureLabel(name: string): string {
  return name.replace(/^q\d+_/, '').replaceAll('_', ' ')
}

export function MethodologyPage() {
  const [results, setResults] = useState<JudgeResults[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .methodology()
      .then((data) => setResults(data.results))
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : 'Could not load eval results',
        ),
      )
  }, [])

  return (
    <main className="page methodology-page">
      <div className="report-header">
        <h1>Methodology</h1>
        <p className="lede">
          ask-harder’s reports are graded by an LLM judge. LLM judges fail in
          known ways — fabricated quotes, invented criteria, drifting scores —
          so ours is tested like code, and the results are published here.
        </p>
      </div>

      <section className="report-block">
        <h3>What is measured</h3>
        <p>
          A fixed benchmark of 10 interview questions, each with an answer key
          and three candidate answers of known quality (bad, mediocre,
          strong), is run against the judge’s <em>raw</em> output — before any
          server-side validation can clean it up. Four properties are
          asserted:
        </p>
        <ul>
          {SUITES.map((suite) => (
            <li key={suite.name}>
              <strong>{suite.name}.</strong> {suite.claim}
            </li>
          ))}
        </ul>
        <p>
          The fixtures, the harness, and these result files are committed to{' '}
          <a
            href="https://github.com/Rahat-Kabir/ask-harder/tree/main/backend/evals"
            target="_blank"
            rel="noreferrer"
          >
            the repository
          </a>{' '}
          — anyone can rerun the suite and check the numbers.
        </p>
      </section>

      {error && <p className="error">{error}</p>}
      {!error && results === null && <LoadingState label="Loading results…" />}
      {results?.length === 0 && (
        <p className="lede">No eval results are published yet.</p>
      )}

      {results?.map((judge) => {
        const answers = answerSetCount(judge.fixtures)
        const repeatRuns =
          answers > 0 ? Math.round(judge.evaluations / answers) : 0
        return (
          <section key={judge.judge_backend} className="report-question">
            <header>
              <span className="question-type">{judge.judge_model}</span>
              {judge.judge_backend === 'mock' && (
                <span className="question-type">
                  harness self-test (deterministic fake judge)
                </span>
              )}
            </header>
            <div className="score-grid">
              <div>
                <span>Ordering</span>
                <strong>{orderingSummary(judge.fixtures)}</strong>
              </div>
              <div>
                <span>Stability</span>
                <strong>{stabilitySummary(judge.fixtures)}</strong>
              </div>
              <div>
                <span>Grounding</span>
                <strong>{percent(judge.grounding.rate)}</strong>
              </div>
              <div>
                <span>Key adherence</span>
                <strong>{percent(judge.key_adherence.rate)}</strong>
              </div>
            </div>
            <p className="methodology-meta">
              {judge.evaluations} gradings of {answers} answers
              {repeatRuns > 1 && ` (${repeatRuns} repeat runs for stability)`}{' '}
              · {judge.grounding.quotes_grounded}/{judge.grounding.quotes_total}{' '}
              quotes verbatim · {judge.key_adherence.points_matched}/
              {judge.key_adherence.points_total} reported gaps from the key ·
              run {new Date(judge.generated_at).toLocaleDateString()}
            </p>
            {answers > 0 && (
              <details className="report-disclosure">
                <summary>Per-question results</summary>
                <div className="methodology-table-wrap">
                  <table className="methodology-table">
                    <thead>
                      <tr>
                        <th>Question</th>
                        <th>Bad</th>
                        <th>Mediocre</th>
                        <th>Strong</th>
                        <th>Ordering</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(judge.fixtures).map(([name, fixture]) => (
                        <tr key={name}>
                          <td>{fixtureLabel(name)}</td>
                          <td>{firstRunOverall(fixture, 'bad')}</td>
                          <td>{firstRunOverall(fixture, 'mediocre')}</td>
                          <td>{firstRunOverall(fixture, 'strong')}</td>
                          <td>
                            {fixture.ordering_ok === undefined
                              ? '—'
                              : fixture.ordering_ok
                                ? '✓'
                                : '✗'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="methodology-meta">
                  Raw judge scores on the native 1–5 scale, first run of each
                  answer.
                </p>
              </details>
            )}
          </section>
        )
      })}

      <section className="report-block">
        <h3>What this doesn’t prove</h3>
        <ul>
          <li>
            The fixture answers are synthetic — drafted by an AI, then
            human-reviewed and labeled. Real candidate answers are messier,
            so this exam is cleaner than production.
          </li>
          <li>
            The strong answers are essay-polished and consistently score 5/5,
            so the benchmark says little about how the judge treats a
            good-but-imperfect human answer.
          </li>
          <li>
            These numbers measure the judge’s raw output on these 30 answers
            only. In production, a validation layer additionally strips any
            ungrounded quote or off-key point before a report reaches you.
          </li>
        </ul>
      </section>

      <Link to="/" className="primary-button report-cta">
        Back to ask-harder
      </Link>
    </main>
  )
}
