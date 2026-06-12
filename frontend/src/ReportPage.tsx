import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type Report } from './api'
import { SESSION_LABELS } from './formatTag'
import { LoadingState } from './LoadingState'

function averageScore(scores: Report['questions'][0]['evaluation']['scores']) {
  const values = [
    scores.correctness,
    scores.depth,
    scores.structure,
    scores.communication,
  ]
  return (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(
    1,
  )
}

export function ReportPage() {
  const { id = '' } = useParams()
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    api
      .getReport(id)
      .then(setReport)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Could not load report'),
      )
  }, [id])

  if (error) {
    return (
      <main className="page report-page">
        <p className="error">{error}</p>
        <Link to="/">Back home</Link>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="page report-page">
        <LoadingState label="Loading report…" />
      </main>
    )
  }

  const overallAverage = (
    report.questions.reduce(
      (sum, question) =>
        sum +
        (question.evaluation.scores.correctness +
          question.evaluation.scores.depth +
          question.evaluation.scores.structure +
          question.evaluation.scores.communication) /
          4,
      0,
    ) / report.questions.length
  ).toFixed(1)

  return (
    <main className="page report-page">
      <div className="report-header">
        <h1>Interview report</h1>
        <p className="lede">
          {report.profile.role} · {report.profile.seniority} ·{' '}
          {SESSION_LABELS[report.session_type]}
        </p>
        <p className="report-overall">
          Overall average: <strong>{overallAverage} / 5</strong>
        </p>
      </div>

      {report.questions.map((question) => (
        <section key={question.position} className="report-question">
          <header>
            <span className="question-index">Q{question.position + 1}</span>
            <span className="question-type">{question.qtype.replace('_', ' ')}</span>
            <span className="question-score">
              {averageScore(question.evaluation.scores)} / 5
            </span>
          </header>

          <h2>{question.text}</h2>

          <div className="score-grid">
            <div>
              <span>Correctness</span>
              <strong>{question.evaluation.scores.correctness}</strong>
            </div>
            <div>
              <span>Depth</span>
              <strong>{question.evaluation.scores.depth}</strong>
            </div>
            <div>
              <span>Structure</span>
              <strong>{question.evaluation.scores.structure}</strong>
            </div>
            <div>
              <span>Communication</span>
              <strong>{question.evaluation.scores.communication}</strong>
            </div>
          </div>

          {question.evaluation.evidence.length > 0 && (
            <div className="report-block">
              <h3>Evidence</h3>
              <ul>
                {question.evaluation.evidence.map((item) => (
                  <li key={item.claim}>
                    <strong>{item.claim}</strong>
                    <blockquote>{item.quote}</blockquote>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {question.evaluation.missing_points.length > 0 && (
            <div className="report-block">
              <h3>Missing from your answer</h3>
              <ul>
                {question.evaluation.missing_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="report-block">
            <h3>Model answer</h3>
            <p>{question.evaluation.model_answer}</p>
          </div>

          <details className="answer-key">
            <summary>Answer key (revealed after interview)</summary>
            <h4>Required</h4>
            <ul>
              {question.answer_key.required_points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
            {question.answer_key.strong_signals.length > 0 && (
              <>
                <h4>Strong signals</h4>
                <ul>
                  {question.answer_key.strong_signals.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </>
            )}
            {question.answer_key.red_flags.length > 0 && (
              <>
                <h4>Red flags</h4>
                <ul>
                  {question.answer_key.red_flags.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </>
            )}
          </details>
        </section>
      ))}

      <div className="report-actions">
        <Link to="/interviews/new" className="primary-button">
          Start another interview
        </Link>
        <Link to="/skills" className="secondary-button">
          View skill tracking
        </Link>
      </div>
    </main>
  )
}
