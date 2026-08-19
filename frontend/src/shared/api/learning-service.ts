import type { BookProgress, BookProgressStatus } from '@/entities/book/types'

import { getToken } from './auth'
import { API_BASE, ApiError, apiRequest } from './http'

export type LearningEventType =
  | 'CHAPTER_STARTED'
  | 'CHAPTER_FINISHED'
  | 'SECTION_READ'
  | 'KNOWLEDGE_CARD_VIEWED'
  | 'HELP_REQUESTED'
  | 'EXPLAIN_REQUESTED'
  | 'SUMMARY_REQUESTED'
  | 'QUIZ_CREATED'
  | 'QUIZ_ANSWERED'
  | 'ANSWER_CORRECT'
  | 'ANSWER_WRONG'
  | 'HINT_REQUESTED'
  | 'QUESTION_ASKED'
  | 'BOOK_STARTED'
  | 'BOOK_FINISHED'
  | 'VOICE_SESSION_STARTED'
  | 'ROLE_SWITCHED'
  | 'TEXT_SELECTED'

export interface LearningSession {
  session_id: string
  student_id: string
  book_id: string
  chapter_id: string
  started_at: string
  ended_at: string | null
  duration_seconds: number
  status: 'ACTIVE' | 'ENDED' | 'ABANDONED'
  entry_route: string | null
  created_at: string
}

export interface CreateLearningSessionInput {
  book_id: string
  chapter_id: string
  entry_route?: string
}

export interface CreateLearningEventInput {
  event_type: LearningEventType
  occurred_at: string
  book_id?: string
  chapter_id?: string
  block_id?: string
  payload?: Record<string, unknown>
}

export interface LearningEvent {
  event_id: string
  student_id: string
  session_id: string | null
  event_type: LearningEventType
  occurred_at: string
  book_id: string | null
  chapter_id: string | null
  block_id: string | null
  knowledge_point_ids: string[]
  payload: Record<string, unknown>
  created_at: string
}

export interface UpsertBookProgressInput {
  chapter_id?: string
  block_id?: string
  status?: BookProgressStatus
  position_percent?: number
}

export interface LearningService {
  createSession(input: CreateLearningSessionInput): Promise<LearningSession>
  endSession(sessionId: string): Promise<LearningSession>
  createEvent(input: CreateLearningEventInput): Promise<LearningEvent>
  upsertProgress(bookId: string, input: UpsertBookProgressInput): Promise<BookProgress>
}

async function apiRequestWithToken<T>(
  path: string,
  token: string,
  options: { method: 'PATCH'; body: unknown },
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(options.body),
  })

  if (response.status === 204) return undefined as T

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

export class ApiLearningService implements LearningService {
  private readonly sessionTokens = new Map<string, string>()

  async createSession(input: CreateLearningSessionInput): Promise<LearningSession> {
    const token = getToken()
    const session = await apiRequest<LearningSession>('/learning-sessions', {
      method: 'POST',
      body: input,
    })
    if (token) this.sessionTokens.set(session.session_id, token)
    return session
  }

  async endSession(sessionId: string): Promise<LearningSession> {
    const token = this.sessionTokens.get(sessionId)
    try {
      if (token) {
        return await apiRequestWithToken<LearningSession>(
          `/learning-sessions/${encodeURIComponent(sessionId)}`,
          token,
          { method: 'PATCH', body: { status: 'ENDED' } },
        )
      }
      return await apiRequest<LearningSession>(
        `/learning-sessions/${encodeURIComponent(sessionId)}`,
        {
          method: 'PATCH',
          body: { status: 'ENDED' },
        },
      )
    } finally {
      this.sessionTokens.delete(sessionId)
    }
  }

  createEvent(input: CreateLearningEventInput): Promise<LearningEvent> {
    return apiRequest<LearningEvent>('/learning-events', {
      method: 'POST',
      body: {
        ...input,
        payload: input.payload ?? {},
      },
    })
  }

  upsertProgress(bookId: string, input: UpsertBookProgressInput): Promise<BookProgress> {
    return apiRequest<BookProgress>(`/me/progress/${encodeURIComponent(bookId)}`, {
      method: 'PUT',
      body: input,
    })
  }
}

export const learningService: LearningService = new ApiLearningService()
