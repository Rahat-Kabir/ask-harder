import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type User } from './api'

type Mode = 'login' | 'register'

// A static sample of a real report — the product's defining moment shown, not
// described. Deliberately harsh and evidence-grounded to match what the judge
// actually produces.
const SAMPLE_SCORES = [
  { label: 'System design', pct: 36, band: 'low', rating: 'Weak' },
  { label: 'Trade-offs', pct: 30, band: 'low', rating: 'Weak' },
  { label: 'Communication', pct: 62, band: 'mid', rating: 'Mixed' },
]

const STEPS = [
  {
    title: 'Paste the JD',
    body: 'Drop in any job description. It reads the role and seniority and builds an interview for that job.',
  },
  {
    title: 'Get interviewed',
    body: 'Live, adaptive questions. Stay vague and it probes harder — like a real interviewer who noticed.',
  },
  {
    title: 'Read the verdict',
    body: 'A scored report: pass, borderline, or no. Per-skill breakdown, every score tied to something you said.',
  },
]

export function AuthPage({ onAuthed }: { onAuthed: (user: User) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const call = mode === 'login' ? api.login : api.register
      onAuthed(await call(email, password))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  return (
    <div className="landing">
      <section className="landing-pitch">
        <header className="landing-hero">
          <p className="landing-brand">ask-harder</p>
          <h1>The interviewer that actually says no.</h1>
          <p className="landing-sub">
            Paste a job description. Take a mock interview tailored to it. Walk
            away with a harsh, evidence-grounded report that quotes what you
            actually said — not "great job."
          </p>
        </header>

        <figure className="landing-proof">
          <figcaption className="landing-proof-cap">Sample report</figcaption>
          <div className="verdict verdict-no">
            <span className="verdict-label">No</span>
            <h3 className="verdict-headline">Doesn't clear the senior bar — yet.</h3>
            <p className="verdict-rationale">
              Fluent on the happy path, but folds on trade-offs and failure
              modes.
            </p>
          </div>
          <blockquote className="landing-proof-quote">
            "I'd just throw a cache in front of it."
            <span> — names no eviction policy, no staleness bound, no failure behavior.</span>
          </blockquote>
          <div className="score-bars">
            {SAMPLE_SCORES.map((score) => (
              <div className="score-bar-row" key={score.label}>
                <span className="score-bar-label">{score.label}</span>
                <div className="score-bar-track">
                  <div
                    className={`score-bar-fill band-${score.band}`}
                    style={{ width: `${score.pct}%` }}
                  />
                </div>
                <span className={`score-bar-rating band-${score.band}`}>
                  {score.rating}
                </span>
              </div>
            ))}
          </div>
        </figure>

        <section className="landing-section landing-steps">
          <p className="landing-eyebrow">How it works</p>
          <ol>
            {STEPS.map((step, index) => (
              <li key={step.title}>
                <span className="landing-step-num">{index + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-section landing-trust">
          <p className="landing-eyebrow">Feedback you can actually trust</p>
          <p>
            Most mock tools flatter you. This one judges every answer against an
            answer key, scores each skill, and grounds every verdict in your own
            transcript. The judge itself is tested on a fixed set of answers —
            strong, mediocre, and bad — so its scoring is measured, not vibes.
          </p>
          <Link to="/methodology" className="landing-link">
            See how we test the judge →
          </Link>
        </section>

        <section className="landing-section landing-memory">
          <p className="landing-eyebrow">It remembers every answer</p>
          <p>
            Nothing is thrown away. Every interview feeds a running picture of
            where you're strong, where you're weak, and whether you're improving
            — so practice compounds instead of resetting each time.
          </p>
        </section>

        <footer className="landing-foot">
          <Link to="/methodology">Methodology</Link>
          <a
            href="https://github.com/Rahat-Kabir/ask-harder"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
          <span className="landing-foot-note">built by Rahat</span>
        </footer>
      </section>

      <aside className="landing-auth">
        <div className="auth-card">
          <p className="auth-card-kicker">
            {mode === 'login' ? 'Welcome back' : 'Start free'}
          </p>
          <div className="mode-switch" role="tablist">
            <button
              role="tab"
              aria-selected={mode === 'login'}
              className={mode === 'login' ? 'active' : ''}
              onClick={() => switchMode('login')}
            >
              Log in
            </button>
            <button
              role="tab"
              aria-selected={mode === 'register'}
              className={mode === 'register' ? 'active' : ''}
              onClick={() => switchMode('register')}
            >
              Register
            </button>
          </div>

          <form onSubmit={submit}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                minLength={mode === 'register' ? 8 : undefined}
                required
              />
              {mode === 'register' && (
                <span className="field-hint">At least 8 characters</span>
              )}
            </label>

            {error && <p className="error">{error}</p>}

            <button type="submit" disabled={busy}>
              {busy ? '…' : mode === 'login' ? 'Log in' : 'Create account'}
            </button>
          </form>
        </div>
      </aside>
    </div>
  )
}
