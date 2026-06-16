import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type SkillAnswer, type SkillDetail } from './api'
import { formatTag } from './formatTag'
import { LoadingState } from './LoadingState'
import { overallOf, SCORE_MAX } from './scoring'
import { useDrill } from './useDrill'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

type TrendPoint = {
  date: string
  average: number
}

// answers come newest-first; one point per interview, oldest first
function trendPoints(answers: SkillAnswer[]): TrendPoint[] {
  const byInterview = new Map<string, { date: string; scores: number[] }>()
  for (const answer of answers) {
    const entry = byInterview.get(answer.interview_id) ?? {
      date: answer.interview_created_at,
      scores: [],
    }
    entry.scores.push(overallOf(answer.scores))
    byInterview.set(answer.interview_id, entry)
  }
  return [...byInterview.values()]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((entry) => ({
      date: entry.date,
      average: entry.scores.reduce((sum, s) => sum + s, 0) / entry.scores.length,
    }))
}

function TrendChart({ points }: { points: TrendPoint[] }) {
  const width = 320
  const height = 80
  const padding = 8
  // y maps a 0..100 score to bottom..top
  const x = (index: number) =>
    padding + (index * (width - 2 * padding)) / (points.length - 1)
  const y = (score: number) =>
    height - padding - (score / SCORE_MAX) * (height - 2 * padding)
  const path = points
    .map((point, index) => `${x(index)},${y(point.average)}`)
    .join(' ')

  return (
    <div className="trend-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Score per interview, oldest to newest: ${points
          .map((point) => Math.round(point.average))
          .join(', ')}`}
      >
        <polyline points={path} fill="none" />
        {points.map((point, index) => (
          <circle key={point.date} cx={x(index)} cy={y(point.average)} r="3" />
        ))}
      </svg>
      <div className="trend-chart-labels">
        <span>{formatDate(points[0].date)}</span>
        <span>{formatDate(points[points.length - 1].date)}</span>
      </div>
    </div>
  )
}

function AnswerCard({ answer }: { answer: SkillAnswer }) {
  return (
    <section className="report-question">
      <header>
        <span className="question-type">{answer.qtype.replace('_', ' ')}</span>
        <span>{formatDate(answer.interview_created_at)}</span>
        <span className="question-score">
          {overallOf(answer.scores)} / {SCORE_MAX}
        </span>
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
  const { startDrill, drilling, drillError } = useDrill()

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

  const points = trendPoints(detail.answers)

  return (
    <main className="page report-page">
      <div className="report-header">
        <h1>{formatTag(detail.tag)}</h1>
        <p className="lede">
          Every judged answer behind this score — the receipts, newest first.
        </p>
        <p className="report-overall">
          Average: <strong>{Math.round(detail.average)} / {SCORE_MAX}</strong>{' '}
          across{' '}
          {detail.evaluation_count}{' '}
          {detail.evaluation_count === 1 ? 'judged answer' : 'judged answers'}
        </p>
        {points.length >= 2 && <TrendChart points={points} />}
        <div className="report-actions">
          <button
            type="button"
            className="primary-button"
            onClick={() => startDrill(detail.tag)}
            disabled={drilling}
          >
            {drilling ? 'Building your drill…' : 'Drill this skill'}
          </button>
        </div>
        {drillError && <p className="error">{drillError}</p>}
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
