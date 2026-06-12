export type User = {
  id: string
  email: string
  created_at: string
  resume_text: string | null
}

export type QuestionType =
  | 'warmup'
  | 'behavioral'
  | 'technical'
  | 'system_design'

export type SessionType = 'screen' | 'round' | 'full_loop'

export type Profile = {
  role: string
  seniority: string
  stack: string[]
  competencies: string[]
  resume_claims: string[]
}

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
  session_type: SessionType
  practice_tag: string | null
  // null for practice drills and while preparing
  profile: Profile | null
  question_count: number
  current_question_position: number | null
  awaiting_answer: boolean
  current_question: InterviewQuestion | null
  turns: Turn[]
}

// exactly one of jd_text / practice_tag
export type CreateInterviewInput = {
  jd_text?: string
  practice_tag?: string
  resume_text?: string
  session_type?: SessionType
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
  // null for practice drills
  profile: Profile | null
  practice_tag: string | null
  session_type: SessionType
  finished_at: string
  questions: ReportQuestion[]
}

export type InterviewSummary = {
  id: string
  status: string
  session_type: SessionType
  practice_tag: string | null
  role: string | null
  seniority: string | null
  question_count: number
  overall_score: number | null
  created_at: string
  finished_at: string | null
}

export type Quota = {
  limit: number
  used_today: number
  remaining: number
  resets_at: string
}

export type Skill = {
  tag: string
  average: number
  evaluation_count: number
  updated_at: string
  // latest-interview average minus previous; null until 2 interviews
  trend: number | null
}

export type SkillAnswer = {
  interview_id: string
  interview_created_at: string
  position: number
  qtype: QuestionType
  question_text: string
  candidate_answers: string[]
  scores: Scores
  evidence: EvidenceItem[]
  missing_points: string[]
  judge_model: string
}

export type SkillDetail = {
  tag: string
  average: number
  evaluation_count: number
  answers: SkillAnswer[]
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

  // permanent: cascades interviews, evaluations, skills, sessions
  deleteMe: () => request<void>('/api/me', { method: 'DELETE' }),

  // blank clears the saved resume
  saveResume: (resumeText: string) =>
    request<User>('/api/me/resume', {
      method: 'PUT',
      body: JSON.stringify({ resume_text: resumeText }),
    }),

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

  getQuota: () => request<Quota>('/api/quota'),

  // fresh interview from a previous one's stored JD/tag, same session type
  retakeInterview: (id: string) =>
    request<{ id: string; status: 'ready' | 'preparing' }>(
      `/api/interviews/${id}/retake`,
      { method: 'POST' },
    ),

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

  // soft delete: hidden everywhere, skill averages recomputed server-side
  deleteInterview: (id: string) =>
    request<void>(`/api/interviews/${id}`, { method: 'DELETE' }),

  getSkills: () => request<{ skills: Skill[] }>('/api/skills'),

  // tag contains a slash ("databases/indexing") — passed through raw,
  // matched server-side by the {tag:path} route
  getSkillDetail: (tag: string) => request<SkillDetail>(`/api/skills/${tag}`),

  methodology: () =>
    request<{ results: JudgeResults[] }>('/api/methodology'),
}
