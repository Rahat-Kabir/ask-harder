import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type JudgeResults } from './api'
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

      {results?.map((judge) => (
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
              <span>Grounding</span>
              <strong>{percent(judge.grounding.rate)}</strong>
            </div>
            <div>
              <span>Key adherence</span>
              <strong>{percent(judge.key_adherence.rate)}</strong>
            </div>
            <div>
              <span>Graded answers</span>
              <strong>{judge.evaluations}</strong>
            </div>
          </div>
          <p className="methodology-meta">
            {judge.grounding.quotes_grounded}/{judge.grounding.quotes_total}{' '}
            quotes verbatim · {judge.key_adherence.points_matched}/
            {judge.key_adherence.points_total} reported gaps from the key ·
            run {new Date(judge.generated_at).toLocaleDateString()}
          </p>
        </section>
      ))}

      <Link to="/" className="primary-button report-cta">
        Back to ask-harder
      </Link>
    </main>
  )
}
