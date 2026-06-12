import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, type Report } from './api'
import { formatTag, SESSION_LABELS } from './formatTag'
import { LoadingState } from './LoadingState'
import { useDrill } from './useDrill'

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

// presentation → last candidate turn, from stored timestamps
function answeredIn(turns: Report['questions'][0]['turns']): string | null {
  if (turns.length === 0) return null
  const presented = new Date(turns[0].created_at).getTime()
  const candidateTimes = turns
    .filter((turn) => turn.role === 'candidate')
    .map((turn) => new Date(turn.created_at).getTime())
  if (candidateTimes.length === 0) return null
  const seconds = Math.max(
    0,
    Math.round((Math.max(...candidateTimes) - presented) / 1000),
  )
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

// the lowest-scoring question's first tag — what to work on next
function weakestArea(
  questions: Report['questions'],
): { tag: string; score: string } | null {
  let weakest: Report['questions'][0] | null = null
  for (const question of questions) {
    if (question.tags.length === 0) continue
    if (
      weakest === null ||
      Number(averageScore(question.evaluation.scores)) <
        Number(averageScore(weakest.evaluation.scores))
    ) {
      weakest = question
    }
  }
  if (!weakest) return null
  return { tag: weakest.tags[0], score: averageScore(weakest.evaluation.scores) }
}

function DeleteInterview({ id }: { id: string }) {
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function deleteInterview() {
    setDeleting(true)
    setError(null)
    try {
      await api.deleteInterview(id)
      navigate('/interviews')
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not delete the interview',
      )
      setDeleting(false)
    }
  }

  return (
    <div className="delete-interview">
      {error && <p className="error">{error}</p>}
      {confirming ? (
        <div className="report-actions">
          <button
            type="button"
            className="danger-button"
            onClick={deleteInterview}
            disabled={deleting}
          >
            {deleting ? 'Deleting…' : 'Yes, delete this interview'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setConfirming(false)}
            disabled={deleting}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="delete-interview-link"
          onClick={() => setConfirming(true)}
        >
          Delete this interview — removes it from history and recalculates
          your skill averages
        </button>
      )}
    </div>
  )
}

export function ReportPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retaking, setRetaking] = useState(false)
  const [retakeError, setRetakeError] = useState<string | null>(null)
  const { startDrill, drilling, drillError } = useDrill()

  async function retake() {
    setRetaking(true)
    setRetakeError(null)
    try {
      const created = await api.retakeInterview(id)
      if (created.status === 'preparing') {
        await api.waitUntilInterviewReady(created.id)
      }
      navigate(`/interviews/${created.id}`)
    } catch (err) {
      setRetakeError(
        err instanceof ApiError ? err.message : 'Could not retake the interview',
      )
      setRetaking(false)
    }
  }

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

  const weakest = weakestArea(report.questions)
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
          {report.practice_tag
            ? `Practice · ${formatTag(report.practice_tag)}`
            : `${report.profile?.role} · ${report.profile?.seniority}`}{' '}
          · {SESSION_LABELS[report.session_type]}
        </p>
        <p className="report-overall">
          Overall average: <strong>{overallAverage} / 5</strong>
        </p>
        <details className="answer-key scoring-legend">
          <summary>How scoring works</summary>
          <p>
            Every answer is scored 1–5 on four dimensions, strictly against a
            rubric frozen before the interview began:
          </p>
          <ul>
            <li>
              <strong>Correctness</strong> — is what you said technically
              right? Wrong claims score low even when said confidently.
            </li>
            <li>
              <strong>Depth</strong> — did you go past the surface:
              trade-offs, failure modes, the <em>why</em> behind the choice?
            </li>
            <li>
              <strong>Structure</strong> — did the answer have a shape
              (context → reasoning → conclusion), or did it ramble?
            </li>
            <li>
              <strong>Communication</strong> — was it clear and precise, with
              correct terms used correctly?
            </li>
          </ul>
          <p>
            Every evidence quote is verified verbatim against your transcript,
            and every "missing" point must come from the frozen answer key —
            the judge can't invent criteria after the fact.
          </p>
        </details>
      </div>

      {report.questions.map((question) => (
        <section key={question.position} className="report-question">
          <header>
            <span className="question-index">Q{question.position + 1}</span>
            <span className="question-type">{question.qtype.replace('_', ' ')}</span>
            {question.evaluation.judge_model === 'skipped' && (
              <span className="skipped-badge">Skipped</span>
            )}
            {answeredIn(question.turns) && (
              <span className="question-time">
                {answeredIn(question.turns)}
              </span>
            )}
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

      {weakest && (
        <section className="report-question report-cta">
          <h2>What to work on next</h2>
          <p>
            Your weakest area this interview:{' '}
            <strong>{formatTag(weakest.tag)}</strong> ({weakest.score} / 5).
          </p>
          {drillError && <p className="error">{drillError}</p>}
          <div className="report-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => startDrill(weakest.tag)}
              disabled={drilling}
            >
              {drilling ? 'Building your drill…' : 'Drill it'}
            </button>
            <Link to={`/skills/${weakest.tag}`} className="secondary-button">
              See the receipts
            </Link>
          </div>
        </section>
      )}

      {retakeError && <p className="error">{retakeError}</p>}
      <div className="report-actions">
        <button
          type="button"
          className="primary-button"
          onClick={retake}
          disabled={retaking}
        >
          {retaking
            ? 'Building your interview…'
            : report.practice_tag
              ? 'Drill this skill again'
              : 'Retake this interview'}
        </button>
        <Link to="/interviews/new" className="secondary-button">
          Start another interview
        </Link>
        <Link to="/skills" className="secondary-button">
          View skill tracking
        </Link>
      </div>

      <DeleteInterview id={report.id} />
    </main>
  )
}
