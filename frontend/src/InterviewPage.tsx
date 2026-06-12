import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { formatTag, SESSION_LABELS } from './formatTag'
import { LoadingState } from './LoadingState'
import { api, ApiError, type InterviewState, type Turn } from './api'

type InterviewProgress = {
  current: number
  total: number
}

function progressFromState(state: InterviewState): InterviewProgress | null {
  if (state.current_question_position === null) return null
  return {
    current: state.current_question_position + 1,
    total: state.question_count,
  }
}

type ChatMessage = {
  id: string
  role: 'interviewer' | 'candidate'
  content: string
  isProbe: boolean
  isSkip?: boolean
  streaming?: boolean
}

function turnsToMessages(turns: Turn[]): ChatMessage[] {
  return turns.map((turn) => ({
    id: turn.id,
    role: turn.role,
    content: turn.content,
    isProbe: turn.is_probe,
    isSkip: turn.is_skip,
  }))
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

// when the current question was presented — the first turn on it; lets a
// reload mid-question keep honest time instead of restarting at 0:00
function questionStartMs(state: InterviewState): number {
  const position = state.current_question_position
  const firstTurn = state.turns.find(
    (turn) => turn.question_position === position,
  )
  return firstTurn ? new Date(firstTurn.created_at).getTime() : Date.now()
}

function canFinish(state: InterviewState): boolean {
  return (
    state.status === 'in_progress' &&
    !state.awaiting_answer &&
    state.current_question_position === state.question_count - 1
  )
}

// pre-start confirmation: show what intake understood before the user
// commits — a wrong parse should be caught here, not on the report
function ReadyCard({
  state,
  onStart,
  starting,
}: {
  state: InterviewState
  onStart: () => void
  starting: boolean
}) {
  return (
    <section className="report-question ready-card">
      {state.practice_tag ? (
        <>
          <h2>Practice drill</h2>
          <p className="ready-summary">
            <strong>{formatTag(state.practice_tag)}</strong> ·{' '}
            {state.question_count} focused questions
          </p>
        </>
      ) : (
        <>
          <h2>We read this job description as</h2>
          <p className="ready-summary">
            <strong>
              {state.profile?.role} · {state.profile?.seniority}
            </strong>{' '}
            · {SESSION_LABELS[state.session_type]} · {state.question_count}{' '}
            questions
          </p>
          {state.profile && state.profile.stack.length > 0 && (
            <ul className="ready-chips" aria-label="Stack">
              {state.profile.stack.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {state.profile && state.profile.competencies.length > 0 && (
            <p className="ready-competencies">
              Will probe: {state.profile.competencies.join(', ')}
            </p>
          )}
        </>
      )}
      <button
        type="button"
        className="primary-button"
        onClick={onStart}
        disabled={starting}
      >
        {starting ? 'Starting…' : 'Start interview'}
      </button>
    </section>
  )
}

export function InterviewPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [awaitingAnswer, setAwaitingAnswer] = useState(false)
  const [canSubmitFinish, setCanSubmitFinish] = useState(false)
  const [answerText, setAnswerText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<InterviewProgress | null>(null)
  const [readyState, setReadyState] = useState<InterviewState | null>(null)
  const [streamConnected, setStreamConnected] = useState(false)
  // soft time pressure: visible elapsed clock per question, no enforcement
  const [elapsedSeconds, setElapsedSeconds] = useState<number | null>(null)
  const questionStartRef = useRef<number | null>(null)

  useEffect(() => {
    const interval = setInterval(() => {
      if (questionStartRef.current !== null) {
        setElapsedSeconds(
          Math.max(
            0,
            Math.floor((Date.now() - questionStartRef.current) / 1000),
          ),
        )
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  function startQuestionClock(startMs: number) {
    questionStartRef.current = startMs
    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
  }

  function stopQuestionClock() {
    questionStartRef.current = null
    setElapsedSeconds(null)
  }
  const bootedRef = useRef(false)
  // true while tokens are building an interviewer message; interviewer_done
  // only awaits an answer when the interviewer actually said something
  const interviewerSpokeRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, awaitingAnswer])

  useEffect(() => {
    if (!id) return

    const source = new EventSource(`/api/interviews/${id}/stream`)

    source.onopen = () => setStreamConnected(true)

    source.addEventListener('token', (event) => {
      const { text } = JSON.parse(event.data) as { text: string }
      interviewerSpokeRef.current = true
      setMessages((previous) => {
        const last = previous[previous.length - 1]
        if (last?.role === 'interviewer' && last.streaming) {
          return [
            ...previous.slice(0, -1),
            { ...last, content: last.content + text },
          ]
        }
        return [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: 'interviewer',
            content: text,
            isProbe: false,
            streaming: true,
          },
        ]
      })
    })

    source.addEventListener('question', (event) => {
      const data = JSON.parse(event.data) as { is_probe: boolean }
      if (data.is_probe) return
      setMessages((previous) => {
        const last = previous[previous.length - 1]
        if (last?.role === 'interviewer' && last.streaming) {
          return [
            ...previous.slice(0, -1),
            { ...last, streaming: false },
          ]
        }
        return previous
      })
    })

    source.addEventListener('interviewer_done', (event) => {
      const data = JSON.parse(event.data) as { is_probe: boolean }
      setMessages((previous) => {
        const last = previous[previous.length - 1]
        if (last?.role === 'interviewer' && last.streaming) {
          return [
            ...previous.slice(0, -1),
            { ...last, streaming: false, isProbe: data.is_probe },
          ]
        }
        if (last?.role === 'interviewer') {
          return [
            ...previous.slice(0, -1),
            { ...last, isProbe: data.is_probe },
          ]
        }
        return previous
      })
      // a done event with no spoken text means "no follow-up" (e.g. the
      // last answer was accepted) — there is nothing to answer
      if (interviewerSpokeRef.current) {
        setAwaitingAnswer(true)
      }
      interviewerSpokeRef.current = false
    })

    source.addEventListener('interview_complete', () => {
      navigate(`/interviews/${id}/report`)
    })

    source.onerror = () => {
      setError('Lost connection to the interview stream.')
    }

    return () => {
      source.close()
      setStreamConnected(false)
    }
  }, [id, navigate])

  useEffect(() => {
    if (!id || !streamConnected || bootedRef.current) return
    bootedRef.current = true

    async function boot() {
      try {
        const state = await api.getInterview(id)
        if (state.status === 'complete') {
          navigate(`/interviews/${id}/report`)
          return
        }
        if (state.status === 'in_progress') {
          setMessages(turnsToMessages(state.turns))
          setAwaitingAnswer(state.awaiting_answer)
          setCanSubmitFinish(canFinish(state))
          setProgress(progressFromState(state))
          if (!canFinish(state)) {
            startQuestionClock(questionStartMs(state))
          }
          return
        }
        if (state.status === 'preparing') {
          setError('Interview is still being prepared. Refresh in a moment.')
          return
        }
        if (state.status === 'abandoned') {
          setError('This interview could not be prepared from the job description.')
          return
        }
        if (state.status === 'ready') {
          // don't auto-start: show what intake parsed and let the user
          // commit explicitly
          setReadyState(state)
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Could not start interview')
      }
    }

    void boot()
  }, [id, navigate, streamConnected])

  async function startInterview() {
    if (!id) return
    setBusy(true)
    setError(null)
    try {
      const started = await api.startInterview(id)
      setReadyState(null)
      setCanSubmitFinish(canFinish(started))
      setProgress(progressFromState(started))
      startQuestionClock(Date.now())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not start interview')
    } finally {
      setBusy(false)
    }
  }

  async function submitAnswer(event: FormEvent) {
    event.preventDefault()
    if (!id || !answerText.trim()) return

    const text = answerText.trim()
    setAnswerText('')
    setAwaitingAnswer(false)
    setBusy(true)
    setError(null)
    setMessages((previous) => [
      ...previous,
      {
        id: crypto.randomUUID(),
        role: 'candidate',
        content: text,
        isProbe: false,
      },
    ])

    try {
      // the POST response is the authoritative state — it corrects anything
      // the SSE handlers guessed wrong
      const state = await api.submitAnswer(id, text)
      setAwaitingAnswer(state.awaiting_answer)
      setCanSubmitFinish(canFinish(state))
      const next = progressFromState(state)
      if (canFinish(state)) {
        stopQuestionClock()
      } else if (next && next.current !== progress?.current) {
        startQuestionClock(Date.now())
      }
      setProgress(next)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit answer')
    } finally {
      setBusy(false)
    }
  }

  async function skipQuestion() {
    if (!id) return
    setAwaitingAnswer(false)
    setBusy(true)
    setError(null)
    setMessages((previous) => [
      ...previous,
      {
        id: crypto.randomUUID(),
        role: 'candidate',
        content: '(skipped)',
        isProbe: false,
        isSkip: true,
      },
    ])

    try {
      const state = await api.skipQuestion(id)
      setAwaitingAnswer(state.awaiting_answer)
      setCanSubmitFinish(canFinish(state))
      const next = progressFromState(state)
      if (canFinish(state)) {
        stopQuestionClock()
      } else if (next && next.current !== progress?.current) {
        startQuestionClock(Date.now())
      }
      setProgress(next)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not skip')
    } finally {
      setBusy(false)
    }
  }

  async function finishInterview() {
    if (!id) return
    setBusy(true)
    setError(null)
    try {
      await api.finishInterview(id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not finish interview')
      setBusy(false)
    }
  }

  return (
    <main className="page interview-page">
      <div className="interview-meta">
        <div className="interview-meta-header">
          <h1>Interview</h1>
          {progress && (
            <span className="question-progress">
              Question {progress.current} of {progress.total}
              {elapsedSeconds !== null && (
                <span className="question-clock">
                  {' '}
                  · {formatElapsed(elapsedSeconds)}
                </span>
              )}
            </span>
          )}
        </div>
        <p className="lede">
          Answer in your own words. The interviewer may probe once before moving on.
        </p>
      </div>

      {readyState && (
        <ReadyCard state={readyState} onStart={startInterview} starting={busy} />
      )}

      {!readyState && (
      <div className="chat-log" role="log" aria-live="polite">
        {messages.length === 0 && !error && (
          <LoadingState label="Starting interview…" />
        )}
        {messages.map((message) => (
          <article
            key={message.id}
            className={`chat-bubble ${message.role}${
              message.isProbe ? ' probe' : ''
            }${message.isSkip ? ' skip' : ''}${
              message.streaming ? ' streaming' : ''
            }`}
          >
            <header>
              {message.role === 'interviewer' ? 'Interviewer' : 'You'}
              {message.isProbe ? ' · follow-up' : ''}
              {message.isSkip ? ' · skipped' : ''}
            </header>
            <p>
              {message.content}
              {message.role === 'interviewer' && message.streaming && (
                <span className="stream-cursor" aria-hidden="true" />
              )}
            </p>
          </article>
        ))}
        <div ref={messagesEndRef} />
      </div>
      )}

      {error && <p className="error chat-error">{error}</p>}

      {busy && !awaitingAnswer && !canSubmitFinish && (
        <p className="status-line lede" role="status">
          Interviewer is thinking…
        </p>
      )}

      {awaitingAnswer && (
        <form className="answer-form" onSubmit={submitAnswer}>
          <label>
            Your answer
            <textarea
              value={answerText}
              onChange={(event) => setAnswerText(event.target.value)}
              rows={4}
              placeholder="Type your answer…"
              disabled={busy}
              required
            />
          </label>
          <div className="answer-actions">
            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? 'Sending…' : 'Send answer'}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={skipQuestion}
              disabled={busy}
              title="Recorded as skipped — scores at the floor, no judging of filler"
            >
              Skip
            </button>
          </div>
        </form>
      )}

      {canSubmitFinish && !awaitingAnswer && (
        <div className="finish-row">
          <p>All questions answered. Ready for your scored report.</p>
          <button
            type="button"
            className="primary-button"
            onClick={finishInterview}
            disabled={busy}
          >
            {busy ? 'Judging…' : 'Finish interview'}
          </button>
        </div>
      )}
    </main>
  )
}
