// 对话 UI 消息类型（0-B §3.2；typing/error/refuse 为客户端瞬态，不落库）

export type ChatMessageKind = 'text' | 'tool' | 'typing' | 'quiz' | 'error' | 'refuse'

export interface ChatMessage {
  id: string
  role: 'user' | 'ai'
  kind: ChatMessageKind
  content: string
  meta?: string
  /** 流式输出中（闪烁光标） */
  streaming?: boolean
  /** quiz 消息载荷（1-H 渲染 quiz 卡；本任务仅占位） */
  quiz?: { sessionId: string } | null
}

/** 27 个 intent + 兜底（0-B §2.4 currentIntentText） */
export type ConversationIntent =
  | 'explain'
  | 'summary'
  | 'quiz'
  | 'check-in'
  | 'selected'
  | 'memory'
  | 'memory-dispute'
  | 'profile-question'
  | 'profile-why-transfer'
  | 'profile-why-pace'
  | 'profile-why-question'
  | 'profile-why-change'
  | 'presence-ask'
  | 'today-learn'
  | 'continue-yesterday'
  | 'recent-status'
  | 'recommend-next'
  | 'book-fit'
  | 'book-why-1'
  | 'book-why-2'
  | 'book-why-3'
  | 'give-example'
  | 'give-hint'
  | 'another-way'
  | 'why-wrong'
  | 'explain-question'
  | 'quiz-requestion'
  | 'quiz-detail'
