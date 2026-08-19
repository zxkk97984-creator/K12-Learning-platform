import type {
  Conversation,
  ConversationChannel,
  ConversationStatus,
  ConversationSummary,
  Message,
  ScreenContext,
} from '@/entities/conversation/types'

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

export interface ConversationService {
  getConversations(): Promise<Conversation[]>
  getConversation(conversationId: string): Promise<Conversation>
  createConversation(input?: CreateConversationInput): Promise<Conversation>
  updateConversation(conversationId: string, patch: UpdateConversationInput): Promise<Conversation>
  getMessages(conversationId: string): Promise<Message[]>
  /** 0-D：真实后端为 SSE 流；Mock 直接返回教师回复消息 */
  sendMessage(conversationId: string, input: SendMessageInput): Promise<Message>
  getSummary(conversationId: string): Promise<ConversationSummary | null>
}
