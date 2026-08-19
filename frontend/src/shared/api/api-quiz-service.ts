import type {
  QuizAnswer,
  QuizInteraction,
  QuizQuestion,
  QuizSession,
} from '@/entities/quiz/types'

import { getToken } from './auth'
import { ApiError, API_BASE, apiRequest } from './http'
import type {
  CreateQuizInput,
  HintResult,
  QuizListParams,
  QuizService,
  QuizSessionDetail,
  SubmitAnswerInput,
} from './quiz-service'

interface ApiQuizSessionDTO {
  quiz_session_id: string
  student_id: string
  conversation_id: string | null
  teacher_role_id: string | null
  book_id: string | null
  chapter_id: string | null
  title: string
  quiz_kind: QuizSession['quiz_kind']
  status: QuizSession['status']
  questions_snapshot?: unknown
  result_summary: QuizSession['result_summary']
  duration_seconds?: number
  ai_feedback: string | null
  model_info?: Record<string, unknown> | null
  skill_version: string
  created_at: string
  updated_at?: string
  completed_at: string | null
}

interface ApiQuizQuestionDTO {
  question_id: string
  quiz_session_id: string
  question_order: number
  question_type: QuizQuestion['question_type']
  stem: string
  options?: unknown
  correct_answer?: Record<string, unknown> | null
  explanation?: string | null
  source_context?: Record<string, unknown> | null
  interaction_policy?: Record<string, unknown> | null
  knowledge_point_ids?: unknown
}

interface ApiQuizAnswerDTO extends QuizAnswer {}
interface ApiQuizInteractionDTO extends QuizInteraction {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

function options(value: unknown): QuizQuestion['options'] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (item): item is QuizQuestion['options'][number] =>
      isRecord(item) && typeof item.key === 'string' && typeof item.text === 'string',
  )
}

function interactionPolicy(value: Record<string, unknown> | null | undefined) {
  return {
    allow_hint: value?.allow_hint !== false,
    max_hint_level:
      typeof value?.max_hint_level === 'number' ? value.max_hint_level : 3,
  }
}

function mapQuestion(dto: ApiQuizQuestionDTO): QuizQuestion {
  return {
    question_id: dto.question_id,
    quiz_session_id: dto.quiz_session_id,
    question_order: dto.question_order,
    question_type: dto.question_type,
    stem: dto.stem,
    options: options(dto.options),
    // The live endpoint intentionally hides these fields until the question is
    // answered. Detail snapshots still contain the authoritative values.
    correct_answer: dto.correct_answer ?? {},
    explanation: dto.explanation ?? '',
    source_context: dto.source_context ?? null,
    interaction_policy: interactionPolicy(dto.interaction_policy),
    knowledge_point_ids: stringArray(dto.knowledge_point_ids),
  }
}

function mapSnapshot(value: unknown): QuizQuestion[] {
  if (!Array.isArray(value)) return []
  return value.filter(isRecord).map((item) => mapQuestion(item as unknown as ApiQuizQuestionDTO))
}

function mapSession(dto: ApiQuizSessionDTO): QuizSessionDetail {
  const session: QuizSessionDetail = {
    quiz_session_id: dto.quiz_session_id,
    student_id: dto.student_id,
    conversation_id: dto.conversation_id,
    // The backend deliberately allows a missing role until Phase 11.
    teacher_role_id: dto.teacher_role_id,
    book_id: dto.book_id,
    chapter_id: dto.chapter_id,
    title: dto.title,
    quiz_kind: dto.quiz_kind,
    status: dto.status,
    result_summary: dto.result_summary,
    ai_feedback: dto.ai_feedback,
    skill_version: dto.skill_version,
    created_at: dto.created_at,
    updated_at: dto.updated_at ?? dto.created_at,
    completed_at: dto.completed_at,
  }
  if (Array.isArray(dto.questions_snapshot)) session.questions_snapshot = mapSnapshot(dto.questions_snapshot)
  if (dto.duration_seconds !== undefined) session.duration_seconds = dto.duration_seconds
  if (dto.model_info !== undefined) session.model_info = dto.model_info
  return session
}

function mapAnswer(dto: ApiQuizAnswerDTO): QuizAnswer {
  return {
    answer_id: dto.answer_id,
    quiz_session_id: dto.quiz_session_id,
    question_id: dto.question_id,
    student_id: dto.student_id,
    submitted_answer: dto.submitted_answer ?? {},
    is_correct: dto.is_correct,
    attempt_no: dto.attempt_no,
    hint_level_at_submit: dto.hint_level_at_submit,
    is_final: dto.is_final,
    submitted_at: dto.submitted_at,
    created_at: dto.created_at,
  }
}

function mapInteraction(dto: ApiQuizInteractionDTO): QuizInteraction {
  return {
    interaction_id: dto.interaction_id,
    quiz_session_id: dto.quiz_session_id,
    question_id: dto.question_id,
    interaction_type: dto.interaction_type,
    payload: dto.payload ?? {},
    message_id: dto.message_id,
    answer_id: dto.answer_id,
    sequence: dto.sequence,
    created_at: dto.created_at,
  }
}

function queryString(params: QuizListParams = {}): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

function requestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function requestWithHeaders<T>(
  path: string,
  body: unknown,
  headers: Record<string, string>,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: JSON.stringify(body),
  })
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; details?: unknown } })
      ?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? `HTTP ${response.status}`,
      error?.details,
    )
  }
  return (payload as { data: T }).data
}

export class ApiQuizService implements QuizService {
  async createQuizSession(input: CreateQuizInput = {}): Promise<QuizSessionDetail> {
    const body = {
      ...(input.conversation_id === undefined ? {} : { conversation_id: input.conversation_id }),
      ...(input.book_id === undefined ? {} : { book_id: input.book_id }),
      ...(input.chapter_id === undefined ? {} : { chapter_id: input.chapter_id }),
      quiz_kind: input.quiz_kind ?? 'CHAPTER_QUIZ',
      question_count: input.question_count ?? 3,
      difficulty: input.difficulty ?? 'MEDIUM',
    }
    return mapSession(
      await apiRequest<ApiQuizSessionDTO>('/quiz-sessions', {
        method: 'POST',
        body,
      }),
    )
  }

  async getQuizSessions(params?: QuizListParams): Promise<QuizSession[]> {
    const payload = await apiRequest<ApiQuizSessionDTO[] | { items: ApiQuizSessionDTO[] }>(
      `/quiz-sessions${queryString(params)}`,
    )
    const rows = Array.isArray(payload) ? payload : payload.items
    return rows.map(mapSession)
  }

  async getQuizSession(quizSessionId: string): Promise<QuizSessionDetail> {
    return mapSession(
      await apiRequest<ApiQuizSessionDTO>(
        `/quiz-sessions/${encodeURIComponent(quizSessionId)}`,
      ),
    )
  }

  async getQuestions(quizSessionId: string): Promise<QuizQuestion[]> {
    const rows = await apiRequest<ApiQuizQuestionDTO[]>(
      `/quiz-sessions/${encodeURIComponent(quizSessionId)}/questions`,
    )
    return rows.map(mapQuestion)
  }

  async submitAnswer(
    quizSessionId: string,
    questionId: string,
    input: SubmitAnswerInput,
    idempotencyKey?: string,
  ): Promise<QuizAnswer> {
    const token = getToken()
    return mapAnswer(
      await requestWithHeaders<ApiQuizAnswerDTO>(
        `/quiz-sessions/${encodeURIComponent(quizSessionId)}/questions/${encodeURIComponent(questionId)}/answers`,
        input,
        {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          'Idempotency-Key': idempotencyKey ?? requestId(),
        },
      ),
    )
  }

  async requestHint(quizSessionId: string, questionId: string): Promise<HintResult> {
    return apiRequest<HintResult>(
      `/quiz-sessions/${encodeURIComponent(quizSessionId)}/questions/${encodeURIComponent(questionId)}/hints`,
      { method: 'POST', body: {} },
    )
  }

  /** Alias matching the contract wording; requestHint remains the shared UI interface. */
  getHints(quizSessionId: string, questionId: string): Promise<HintResult> {
    return this.requestHint(quizSessionId, questionId)
  }

  async getAnswers(quizSessionId: string): Promise<QuizAnswer[]> {
    const rows = await apiRequest<ApiQuizAnswerDTO[]>(
      `/quiz-sessions/${encodeURIComponent(quizSessionId)}/answers`,
    )
    return rows.map(mapAnswer)
  }

  async getInteractions(quizSessionId: string): Promise<QuizInteraction[]> {
    const rows = await apiRequest<ApiQuizInteractionDTO[]>(
      `/quiz-sessions/${encodeURIComponent(quizSessionId)}/interactions`,
    )
    return rows.map(mapInteraction)
  }
}
