// 测验域类型（对齐 0-C/0-D；枚举与总控 §15.4 一致）

export type QuizKind = 'CHAPTER_QUIZ' | 'AI_QUIZ'
export type QuizStatus = 'GENERATING' | 'ACTIVE' | 'COMPLETED' | 'ABANDONED'
export type QuizQuestionType = 'SINGLE_CHOICE' | 'MULTIPLE_CHOICE' | 'TRUE_FALSE' | 'FILL_BLANK'
export type QuizInteractionType =
  | 'HINT_REQUEST'
  | 'HINT_RESPONSE'
  | 'QUESTION_ASK'
  | 'TEACHER_REPLY'
  | 'ANSWER_SUBMIT'
  | 'ANSWER_RESULT'

export interface QuizOption {
  key: string
  text: string
}

export interface InteractionPolicy {
  allow_hint: boolean
  max_hint_level: number
}

export interface QuizResultSummary {
  correct: number
  total: number
  hints_used: number
}

export interface QuizQuestion {
  question_id: string
  quiz_session_id: string
  question_order: number
  question_type: QuizQuestionType
  stem: string
  options: QuizOption[]
  /** 服务端权威；live 阶段按条件可见（0-D §3.6） */
  correct_answer: Record<string, unknown>
  explanation: string
  source_context: Record<string, unknown> | null
  interaction_policy: InteractionPolicy
  knowledge_point_ids: string[]
}

export interface QuizSession {
  quiz_session_id: string
  student_id: string
  conversation_id: string | null
  teacher_role_id: string
  book_id: string | null
  chapter_id: string | null
  title: string
  quiz_kind: QuizKind
  status: QuizStatus
  /** (derived) 原型 score「8 / 10」→ { correct: 8, total: 10 } */
  result_summary: QuizResultSummary | null
  ai_feedback: string | null
  skill_version: string
  /** 展示日期由 created_at 派生（原型 date 字段） */
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface QuizAnswer {
  answer_id: string
  quiz_session_id: string
  question_id: string
  student_id: string
  submitted_answer: Record<string, unknown>
  is_correct: boolean
  attempt_no: number
  hint_level_at_submit: number
  is_final: boolean
  submitted_at: string
  created_at: string
}

export interface QuizInteraction {
  interaction_id: string
  quiz_session_id: string
  question_id: string | null
  interaction_type: QuizInteractionType
  payload: Record<string, unknown>
  message_id: string | null
  answer_id: string | null
  sequence: number
  created_at: string
}
