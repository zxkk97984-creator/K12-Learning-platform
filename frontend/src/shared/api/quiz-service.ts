import type {
  QuizAnswer,
  QuizInteraction,
  QuizKind,
  QuizQuestion,
  QuizSession,
  QuizStatus,
} from '@/entities/quiz/types'

export type QuizDifficulty = 'EASY' | 'MEDIUM' | 'HARD'

export interface QuizSessionDetail extends QuizSession {
  /** Immutable question snapshot returned by GET /quiz-sessions/{id}. */
  questions_snapshot?: QuizQuestion[]
  duration_seconds?: number
  model_info?: Record<string, unknown> | null
}

export interface QuizListParams {
  cursor?: string
  limit?: number
  quiz_kind?: QuizKind
  status?: QuizStatus
  book_id?: string
  date_from?: string
  date_to?: string
}

export interface CreateQuizInput {
  conversation_id?: string | null
  book_id?: string | null
  chapter_id?: string | null
  quiz_kind?: QuizKind
  question_count?: number
  difficulty?: QuizDifficulty
}

export interface SubmitAnswerInput {
  answer: Record<string, unknown>
  hint_level_at_submit?: number
}

export interface HintResult {
  hint_level: number
  hint_text: string
  max_hint_level: number
}

export interface QuizService {
  getQuizSessions(params?: QuizListParams): Promise<QuizSession[]>
  getQuizSession(quizSessionId: string): Promise<QuizSessionDetail>
  /** 0-D：POST /quiz-sessions（真实后端 202 + 轮询；Mock 同步返回 ACTIVE） */
  createQuizSession(input?: CreateQuizInput): Promise<QuizSession>
  getQuestions(quizSessionId: string): Promise<QuizQuestion[]>
  submitAnswer(
    quizSessionId: string,
    questionId: string,
    input: SubmitAnswerInput,
    idempotencyKey?: string,
  ): Promise<QuizAnswer>
  requestHint(quizSessionId: string, questionId: string): Promise<HintResult>
  getAnswers(quizSessionId: string): Promise<QuizAnswer[]>
  getInteractions(quizSessionId: string): Promise<QuizInteraction[]>
}
