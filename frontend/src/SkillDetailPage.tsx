import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type SkillAnswer, type SkillDetail } from './api'
import { formatTag } from './formatTag'
import { LoadingState } from './LoadingState'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function averageScore(scores: SkillAnswer['scores']): string {
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

function AnswerCard({ answer }: { answer: SkillAnswer }) {
  return (
    <section className="report-question">
      <header>
        <span className="question-type">{answer.qtype.replace('_', ' ')}</span>
        <span>{formatDate(answer.interview_created_at)}</span>
        <span className="question-score">{averageScore(answer.scores)} / 5</span>
      </header>

      <h2>{answer.question_text}</h2>

      <div className="score-grid">
        <div>
          <span>Correctness</span>
          <strong>{answer.scores.correctness}</strong>
        </div>
        <div>
          <span>Depth</span>
          <strong>{answer.scores.depth}</strong>
        </div>
        <div>
          <span>Structure</span>
          <strong>{answer.scores.structure}</strong>
        </div>
        <div>
          <span>Communication</span>
          <strong>{answer.scores.communication}</strong>
        </div>
      </div>

      {answer.candidate_answers.length > 0 && (
        <div className="report-block">
          <h3>Your answer</h3>
          {answer.candidate_answers.map((text, index) => (
            <blockquote key={index}>{text}</blockquote>
          ))}
        </div>
      )}

      {answer.evidence.length > 0 && (
        <div className="report-block">
          <h3>Evidence</h3>
          <ul>
            {answer.evidence.map((item) => (
              <li key={item.claim}>
                <strong>{item.claim}</strong>
                <blockquote>{item.quote}</blockquote>
              </li>
            ))}
          </ul>
        </div>
      )}

      {answer.missing_points.length > 0 && (
        <div className="report-block">
          <h3>Missing from your answer</h3>
          <ul>
            {answer.missing_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="skill-meta">
        Judged by {answer.judge_model} ·{' '}
        <Link to={`/interviews/${answer.interview_id}/report`}>
          Full interview report
        </Link>
      </p>
    </section>
  )
}

export function SkillDetailPage() {
  // tags contain slashes, so the route is a splat: /skills/databases/indexing
  const tag = useParams()['*'] ?? ''
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!tag) return
    api
      .getSkillDetail(tag)
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Could not load skill'),
      )
  }, [tag])

  if (error) {
    return (
      <main className="page skills-page">
        <p className="error">{error}</p>
        <Link to="/skills">Back to skills</Link>
      </main>
    )
  }

  if (!detail) {
    return (
      <main className="page skills-page">
        <LoadingState label="Loading skill…" />
      </main>
    )
  }

  return (
    <main className="page report-page">
      <div className="report-header">
        <h1>{formatTag(detail.tag)}</h1>
        <p className="lede">
          Every judged answer behind this score — the receipts, newest first.
        </p>
        <p className="report-overall">
          Average: <strong>{detail.average.toFixed(1)} / 5</strong> across{' '}
          {detail.evaluation_count}{' '}
          {detail.evaluation_count === 1 ? 'judged answer' : 'judged answers'}
        </p>
      </div>

      {detail.answers.map((answer) => (
        <AnswerCard
          key={`${answer.interview_id}-${answer.position}`}
          answer={answer}
        />
      ))}

      <div className="report-actions">
        <Link to="/skills" className="secondary-button">
          Back to skill tracking
        </Link>
      </div>
    </main>
  )
}
