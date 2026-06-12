import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import {
  api,
  ApiError,
  type InterviewSummary,
  type Quota,
  type Skill,
} from './api'
import { formatTag } from './formatTag'
import type { LayoutContext } from './Layout'
import { LoadingState } from './LoadingState'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

type Stats = {
  interviews: InterviewSummary[]
  skills: Skill[]
  quota: Quota
}

function StatsGrid({ interviews, skills, quota }: Stats) {
  const completed = interviews.filter((i) => i.status === 'complete')
  const scored = interviews.filter((i) => i.overall_score !== null)
  const overallAverage =
    scored.length > 0
      ? (
          scored.reduce((sum, i) => sum + (i.overall_score as number), 0) /
          scored.length
        ).toFixed(1) + ' / 5'
      : '—'
  const judgedAnswers = skills.reduce(
    (sum, skill) => sum + skill.evaluation_count,
    0,
  )
  // skills arrive weakest-first from the API
  const weakest = skills[0]
  const strongest = skills.length > 1 ? skills[skills.length - 1] : null

  return (
    <div className="score-grid profile-stats">
      <div>
        <span>Interviews taken</span>
        <strong>{interviews.length}</strong>
      </div>
      <div>
        <span>Completed</span>
        <strong>{completed.length}</strong>
      </div>
      <div>
        <span>Overall average</span>
        <strong>{overallAverage}</strong>
      </div>
      <div>
        <span>Judged answers</span>
        <strong>{judgedAnswers}</strong>
      </div>
      <div>
        <span>Weakest skill</span>
        <strong>{weakest ? formatTag(weakest.tag) : '—'}</strong>
      </div>
      <div>
        <span>Strongest skill</span>
        <strong>{strongest ? formatTag(strongest.tag) : '—'}</strong>
      </div>
      <div>
        <span>Interviews left today</span>
        <strong>
          {quota.remaining} of {quota.limit}
        </strong>
      </div>
    </div>
  )
}

function ResumeEditor({ initial }: { initial: string }) {
  const [text, setText] = useState(initial)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const user = await api.saveResume(text)
      setText(user.resume_text ?? '')
      setSavedAt(Date.now())
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not save the resume',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="report-question">
      <h2>Resume</h2>
      <p className="profile-danger-warning">
        Saved once, auto-filled into every new interview — questions can probe
        your actual claims.
      </p>
      <label className="resume-label">
        <textarea
          value={text}
          onChange={(event) => {
            setText(event.target.value)
            setSavedAt(null)
          }}
          rows={6}
          placeholder="Paste resume highlights — claims an interviewer could probe."
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="report-actions">
        <button
          type="button"
          className="primary-button"
          onClick={save}
          disabled={saving}
        >
          {saving ? 'Saving…' : 'Save resume'}
        </button>
        {savedAt !== null && <p className="quota-line">Saved.</p>}
      </div>
    </section>
  )
}

function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function deleteAccount() {
    setDeleting(true)
    setError(null)
    try {
      await api.deleteMe()
      onDeleted()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not delete the account',
      )
      setDeleting(false)
    }
  }

  return (
    <section className="report-question profile-danger">
      <h2>Delete account</h2>
      <p className="profile-danger-warning">
        Permanently deletes your account and everything in it — interviews,
        reports, and skill history. This cannot be undone.
      </p>
      {error && <p className="error">{error}</p>}
      {confirming ? (
        <div className="report-actions">
          <button
            type="button"
            className="danger-button"
            onClick={deleteAccount}
            disabled={deleting}
          >
            {deleting ? 'Deleting…' : 'Yes, delete everything'}
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
          className="danger-button"
          onClick={() => setConfirming(true)}
        >
          Delete account
        </button>
      )}
    </section>
  )
}

export function ProfilePage() {
  const { user, onLogout } = useOutletContext<LayoutContext>()
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.listInterviews(), api.getSkills(), api.getQuota()])
      .then(([interviewsData, skillsData, quota]) =>
        setStats({
          interviews: interviewsData.interviews,
          skills: skillsData.skills,
          quota,
        }),
      )
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : 'Could not load profile',
        ),
      )
  }, [])

  return (
    <main className="page profile-page">
      <div className="report-header">
        <h1>Profile</h1>
        <p className="lede">
          {user.email} · member since {formatDate(user.created_at)}
        </p>
      </div>

      <section className="report-question">
        <h2>Your numbers</h2>
        {error && <p className="error">{error}</p>}
        {!error &&
          (stats ? (
            <StatsGrid
              interviews={stats.interviews}
              skills={stats.skills}
              quota={stats.quota}
            />
          ) : (
            <LoadingState label="Loading stats…" />
          ))}
        <div className="report-actions">
          <Link to="/interviews" className="secondary-button">
            Interview history
          </Link>
          <Link to="/skills" className="secondary-button">
            Skill tracking
          </Link>
        </div>
      </section>

      <ResumeEditor initial={user.resume_text ?? ''} />

      <DeleteAccount onDeleted={onLogout} />
    </main>
  )
}
