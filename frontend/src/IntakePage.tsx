import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, type SessionType } from './api'

const SESSION_OPTIONS: {
  value: SessionType
  title: string
  questions: number
  minutes: number
  pitch: string
}[] = [
  {
    value: 'screen',
    title: 'Screen',
    questions: 3,
    minutes: 15,
    pitch: 'Quick readiness check',
  },
  {
    value: 'round',
    title: 'Round',
    questions: 5,
    minutes: 30,
    pitch: 'The standard session',
  },
  {
    value: 'full_loop',
    title: 'Full loop',
    questions: 7,
    minutes: 60,
    pitch: 'Pre-interview stress test',
  },
]

export function IntakePage() {
  const navigate = useNavigate()
  const [jdText, setJdText] = useState('')
  const [resumeText, setResumeText] = useState('')
  const [sessionType, setSessionType] = useState<SessionType>('round')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [statusLine, setStatusLine] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setStatusLine(null)
    try {
      const created = await api.createInterview({
        jd_text: jdText,
        resume_text: resumeText.trim() || undefined,
        session_type: sessionType,
      })
      if (created.status === 'preparing') {
        setStatusLine('Tailoring questions to the job description…')
        await api.waitUntilInterviewReady(created.id)
      }
      navigate(`/interviews/${created.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page intake-page">
      <h1>Paste the job description</h1>
      <p className="lede">
        We&apos;ll build a mock interview from the role requirements.
      </p>

      <form className="intake-form" onSubmit={submit}>
        <label>
          Job description
          <textarea
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            rows={10}
            placeholder="Backend Engineer — Python, FastAPI, Postgres…"
            required
          />
        </label>

        <label>
          Resume (optional)
          <textarea
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            rows={5}
            placeholder="Paste resume highlights — claims we can probe in the interview."
          />
        </label>

        <fieldset className="session-picker">
          <legend>Session</legend>
          <div className="session-options">
            {SESSION_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={
                  sessionType === option.value
                    ? 'session-card selected'
                    : 'session-card'
                }
              >
                <input
                  type="radio"
                  name="session_type"
                  value={option.value}
                  checked={sessionType === option.value}
                  onChange={() => setSessionType(option.value)}
                />
                <span className="session-card-title">{option.title}</span>
                <span className="session-card-meta">
                  {option.questions} questions · ~{option.minutes} min
                </span>
                <span className="session-card-pitch">{option.pitch}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {error && <p className="error">{error}</p>}

        {statusLine && (
          <p className="status-line lede" role="status">
            {statusLine}
          </p>
        )}

        <button type="submit" className="primary-button" disabled={busy}>
          {busy ? 'Building your interview…' : 'Create interview'}
        </button>
      </form>
    </main>
  )
}
