import type {
  QuizAnswer,
  QuizInteraction,
  QuizKind,
  QuizQuestion,
  QuizSession,
} from '@/entities/quiz/types'

export interface CreateQuizInput {
  conversation_id?: string | null
  book_id?: string | null
  chapter_id?: string | null
  quiz_kind?: QuizKind
  question_count?: number
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
  getQuizSessions(): Promise<QuizSession[]>
  getQuizSession(quizSessionId: string): Promise<QuizSession>
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
