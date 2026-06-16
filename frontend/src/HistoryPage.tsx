import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type InterviewSummary } from './api'
import { formatTag, SESSION_LABELS } from './formatTag'
import { LoadingState } from './LoadingState'
import { SCORE_MAX } from './scoring'

const STATUS_LABELS: Record<string, string> = {
  preparing: 'Preparing',
  ready: 'Ready',
  in_progress: 'In progress',
  judging: 'Judging',
  complete: 'Complete',
  abandoned: 'Abandoned',
}

function interviewPath(interview: InterviewSummary): string | null {
  if (interview.status === 'complete') {
    return `/interviews/${interview.id}/report`
  }
  if (['ready', 'in_progress', 'judging'].includes(interview.status)) {
    return `/interviews/${interview.id}`
  }
  // preparing has nothing to show yet; abandoned has nothing to resume
  return null
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function HistoryRow({
  interview,
  onDelete,
}: {
  interview: InterviewSummary
  onDelete: (id: string) => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const path = interviewPath(interview)
  // complete interviews have a delete action on their report page
  const canDelete = interview.status !== 'complete'

  const title = interview.practice_tag
    ? `Practice · ${formatTag(interview.practice_tag)}`
    : interview.role
      ? `${interview.role} · ${interview.seniority}`
      : 'Preparing…'

  async function handleDelete() {
    setDeleting(true)
    try {
      await api.deleteInterview(interview.id)
      onDelete(interview.id)
    } catch {
      setDeleting(false)
      setConfirming(false)
    }
  }

  const body = (
    <>
      <div className="history-row-header">
        <span className="history-title">
          {title}
          {` · ${SESSION_LABELS[interview.session_type]}`}
        </span>
        {interview.overall_score !== null && (
          <span className="history-score">
            {Math.round(interview.overall_score)} / {SCORE_MAX}
          </span>
        )}
      </div>
      <p className="history-meta">
        <span className={`status-badge status-${interview.status}`}>
          {STATUS_LABELS[interview.status] ?? interview.status}
        </span>
        {interview.question_count > 0 &&
          ` · ${interview.question_count} questions`}
        {` · ${formatDate(interview.created_at)}`}
      </p>
    </>
  )

  return (
    <li className="history-row">
      <div className="history-row-inner">
        {path ? (
          <Link to={path} className="history-link">
            {body}
          </Link>
        ) : (
          <div className="history-link history-link-disabled">{body}</div>
        )}
        {canDelete && (
          <div className="history-row-delete">
            {confirming ? (
              <>
                <span className="history-delete-prompt">Delete?</span>
                <button
                  className="history-delete-confirm"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? '…' : 'Yes'}
                </button>
                <button
                  className="history-delete-cancel"
                  onClick={() => setConfirming(false)}
                  disabled={deleting}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                className="history-delete-btn"
                onClick={() => setConfirming(true)}
                title="Delete this interview"
                aria-label="Delete this interview"
              >
                ×
              </button>
            )}
          </div>
        )}
      </div>
    </li>
  )
}

export function HistoryPage() {
  const [interviews, setInterviews] = useState<InterviewSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listInterviews()
      .then((data) => setInterviews(data.interviews))
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : 'Could not load interviews',
        ),
      )
  }, [])

  function handleDelete(id: string) {
    setInterviews((prev) => (prev ? prev.filter((i) => i.id !== id) : null))
  }

  if (error) {
    return (
      <main className="page history-page">
        <p className="error">{error}</p>
        <Link to="/">Back home</Link>
      </main>
    )
  }

  if (!interviews) {
    return (
      <main className="page history-page">
        <LoadingState label="Loading interviews…" />
      </main>
    )
  }

  return (
    <main className="page history-page">
      <div className="report-header">
        <h1>Interview history</h1>
        <p className="lede">
          Every interview you've taken — open a report or pick up where you
          left off.
        </p>
      </div>

      {interviews.length === 0 ? (
        <div className="skills-empty">
          <p>No interviews yet. Paste a job description to take your first.</p>
          <Link to="/interviews/new" className="primary-button">
            Start interview
          </Link>
        </div>
      ) : (
        <ul className="history-list">
          {interviews.map((interview) => (
            <HistoryRow
              key={interview.id}
              interview={interview}
              onDelete={handleDelete}
            />
          ))}
        </ul>
      )}
    </main>
  )
}
