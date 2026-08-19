// 对话域类型（对齐 0-C/0-D；Message.type 固定 7 值，总控 §13.2）

export type MessageRole = 'STUDENT' | 'TEACHER' | 'SYSTEM'
export type MessageType =
  | 'TEXT'
  | 'QUIZ'
  | 'TOOL_STATUS'
  | 'HINT'
  | 'RECOMMENDATION'
  | 'SYSTEM'
  | 'LEARNING_SUMMARY'

export type ConversationStatus = 'ACTIVE' | 'ARCHIVED' | 'DELETED'
export type ConversationChannel = 'TEXT' | 'VOICE'

/** 架构 §8 Screen Context 结构 */
export interface ScreenContext {
  route: string
  page_type: string
  book_id?: string
  chapter_id?: string
  chapter_title?: string
  content_block_id?: string
  visible_section?: string
  /** 原型 JSON 为 null；0-D ScreenContext 可选 */
  selected_text?: string | null
  knowledge_points?: string[]
  actions?: string[]
}

export interface Message {
  message_id: string
  conversation_id: string
  role: MessageRole
  type: MessageType
  content: string
  /** 0-D：quiz_session_id / hint_level / tool_state 等 */
  metadata: Record<string, unknown>
  sequence: number
  model_info: { provider: string; model: string } | null
  created_at: string
}

export interface Conversation {
  conversation_id: string
  student_id: string
  teacher_role_id: string
  title: string | null
  status: ConversationStatus
  channel: ConversationChannel
  /** 0-D POST messages 时随请求更新 */
  current_page_context: ScreenContext | null
  /** 缓存窗口，事实源在 messages（0-C） */
  recent_messages: Message[]
  conversation_summary: string | null
  created_at: string
  updated_at: string
  last_message_at: string | null
}

export interface ConversationSummary {
  summary_id: string
  conversation_id: string
  summary: string
  token_count: number
  summary_version: number
  source_message_ids: string[]
  model_info: { provider: string; model: string } | null
  updated_at: string
}
