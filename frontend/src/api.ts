export type User = {
  id: string
  email: string
  created_at: string
}

export type QuestionType =
  | 'warmup'
  | 'behavioral'
  | 'technical'
  | 'system_design'

export type InterviewQuestion = {
  position: number
  qtype: QuestionType
  text: string
}

export type Turn = {
  id: string
  role: 'interviewer' | 'candidate'
  content: string
  is_probe: boolean
  question_position: number
  created_at: string
}

export type InterviewState = {
  id: string
  status: string
  dev_mode: boolean
  question_count: number
  current_question_position: number | null
  awaiting_answer: boolean
  current_question: InterviewQuestion | null
  turns: Turn[]
}

export type CreateInterviewInput = {
  jd_text: string
  resume_text?: string
  dev_mode?: boolean
}

export type Scores = {
  correctness: number
  depth: number
  structure: number
  communication: number
}

export type EvidenceItem = {
  claim: string
  quote: string
}

export type AnswerKey = {
  required_points: string[]
  strong_signals: string[]
  red_flags: string[]
}

export type ReportQuestion = {
  position: number
  qtype: QuestionType
  text: string
  tags: string[]
  answer_key: AnswerKey
  turns: Turn[]
  evaluation: {
    scores: Scores
    evidence: EvidenceItem[]
    missing_points: string[]
    model_answer: string
    judge_model: string
  }
}

export type Report = {
  id: string
  status: 'complete'
  profile: {
    role: string
    seniority: string
    stack: string[]
    competencies: string[]
    resume_claims: string[]
  }
  dev_mode: boolean
  finished_at: string
  questions: ReportQuestion[]
}

export type InterviewSummary = {
  id: string
  status: string
  dev_mode: boolean
  role: string | null
  seniority: string | null
  question_count: number
  overall_score: number | null
  created_at: string
  finished_at: string | null
}

export type Skill = {
  tag: string
  average: number
  evaluation_count: number
  updated_at: string
}

export type JudgeResults = {
  judge_backend: string
  judge_model: string
  generated_at: string
  evaluations: number
  grounding: { quotes_total: number; quotes_grounded: number; rate: number | null }
  key_adherence: { points_total: number; points_matched: number; rate: number | null }
  fixtures: Record<string, { ordering_ok?: boolean }>
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  me: () => request<User>('/api/me'),

  register: (email: string, password: string) =>
    request<User>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<User>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),

  createInterview: (input: CreateInterviewInput) =>
    request<{ id: string; status: 'ready' | 'preparing' }>('/api/interviews', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  waitUntilInterviewReady: async (
    id: string,
    options?: { intervalMs?: number; timeoutMs?: number },
  ): Promise<InterviewState> => {
    const intervalMs = options?.intervalMs ?? 1000
    const timeoutMs = options?.timeoutMs ?? 120_000
    const deadline = Date.now() + timeoutMs

    while (Date.now() < deadline) {
      const state = await api.getInterview(id)
      if (state.status === 'ready') return state
      if (state.status === 'abandoned') {
        throw new ApiError(
          422,
          'Could not prepare the interview from that job description.',
        )
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }

    throw new ApiError(504, 'Interview preparation timed out.')
  },

  listInterviews: () =>
    request<{ interviews: InterviewSummary[] }>('/api/interviews'),

  getInterview: (id: string) =>
    request<InterviewState>(`/api/interviews/${id}`),

  startInterview: (id: string) =>
    request<InterviewState>(`/api/interviews/${id}/start`, { method: 'POST' }),

  submitAnswer: (id: string, text: string) =>
    request<InterviewState>(`/api/interviews/${id}/answer`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  finishInterview: (id: string) =>
    request<InterviewState>(`/api/interviews/${id}/finish`, { method: 'POST' }),

  getReport: (id: string) => request<Report>(`/api/interviews/${id}/report`),

  getSkills: () => request<{ skills: Skill[] }>('/api/skills'),

  methodology: () =>
    request<{ results: JudgeResults[] }>('/api/methodology'),
}
