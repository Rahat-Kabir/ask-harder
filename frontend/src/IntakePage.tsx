import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from './api'

export function IntakePage() {
  const navigate = useNavigate()
  const [jdText, setJdText] = useState('')
  const [resumeText, setResumeText] = useState('')
  const [devMode, setDevMode] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await api.createInterview({
        jd_text: jdText,
        resume_text: resumeText.trim() || undefined,
        dev_mode: devMode,
      })
      if (created.status === 'preparing') {
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
        We&apos;ll build a short mock interview from the role requirements.
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

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={devMode}
            onChange={(event) => setDevMode(event.target.checked)}
          />
          Dev mode (3 questions instead of 7)
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit" className="primary-button" disabled={busy}>
          {busy ? 'Building your interview…' : 'Create interview'}
        </button>
      </form>
    </main>
  )
}
