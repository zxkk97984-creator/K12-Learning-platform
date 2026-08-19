import type {
  Conversation,
  ConversationChannel,
  ConversationListItem,
  ConversationStatus,
  ConversationSummary,
  Message,
} from '@/entities/conversation/types'
import type { ScreenContext } from '@/features/screen-context/types'

export interface CreateConversationInput {
  teacher_role_id?: string
  channel?: ConversationChannel
  title?: string | null
}

export interface UpdateConversationInput {
  title?: string
  status?: ConversationStatus
}

export interface SendMessageInput {
  content: string
  screen_context?: ScreenContext
}

export interface ConversationListParams {
  cursor?: string
  limit?: number
  status?: ConversationStatus
  channel?: ConversationChannel
}

export interface MessageListParams {
  cursor?: string
  limit?: number
  sort?: 'asc' | 'desc'
}

export interface MessageStartEvent {
  message_id: string
  conversation_id: string
  role: 'TEACHER'
  type: 'TEXT'
  sequence: number
  created_at?: string
  request_id?: string
}

export interface TextDeltaEvent {
  message_id: string
  delta: string
  index?: number
  sequence?: number
}

export interface ToolStartEvent {
  tool_run_id: string
  tool: string
  state: string
  message_id?: string
  payload?: Record<string, unknown>
}

export interface ToolResultEvent {
  tool_run_id: string
  tool: string
  status: 'success' | 'error'
  payload?: Record<string, unknown>
}

export interface TextDoneEvent {
  message_id: string
  content: string
  model_info?: { provider: string; model: string } | null
  usage?: Record<string, unknown>
}

export interface MessageDoneEvent {
  message_id: string
  conversation_id: string
  sequence: number
  created_at?: string
  metadata?: Record<string, unknown>
}

export interface StreamErrorEvent {
  request_id?: string
  code: string
  message: string
  details?: unknown
  fatal?: boolean
}

export interface SendMessageCallbacks {
  signal?: AbortSignal
  onStart?: (event: MessageStartEvent) => void
  onDelta?: (event: TextDeltaEvent) => void
  onToolStart?: (event: ToolStartEvent) => void
  onToolResult?: (event: ToolResultEvent) => void
  onTextDone?: (event: TextDoneEvent) => void
  onDone?: (event: MessageDoneEvent) => void
  onError?: (event: StreamErrorEvent | Error) => void
}

export interface ConversationService {
  getConversations(params?: ConversationListParams): Promise<ConversationListItem[]>
  getConversation(conversationId: string): Promise<Conversation>
  createConversation(input?: CreateConversationInput): Promise<Conversation>
  updateConversation(conversationId: string, patch: UpdateConversationInput): Promise<Conversation>
  getMessages(conversationId: string, params?: MessageListParams): Promise<Message[]>
  sendMessage(
    conversationId: string,
    input: SendMessageInput,
    callbacks?: SendMessageCallbacks,
  ): Promise<void>
  sendMessage(
    conversationId: string,
    content: string,
    screenContext?: ScreenContext,
    callbacks?: SendMessageCallbacks,
  ): Promise<void>
  getSummary(conversationId: string): Promise<ConversationSummary | null>
}
