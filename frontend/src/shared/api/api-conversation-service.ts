import type {
  Conversation,
  ConversationListItem,
  ConversationStatus,
  ConversationSummary,
  Message,
} from '@/entities/conversation/types'
import type { ScreenContext } from '@/features/screen-context/types'

import { API_BASE, apiRequest } from './http'
import {
  fetchSSE,
  type FetchSSEOptions,
} from './sse'
import type {
  ConversationListParams,
  ConversationService,
  CreateConversationInput,
  MessageDoneEvent,
  MessageListParams,
  MessageStartEvent,
  SendMessageCallbacks,
  SendMessageInput,
  StreamErrorEvent,
  TextDeltaEvent,
  TextDoneEvent,
  ToolResultEvent,
  ToolStartEvent,
  UpdateConversationInput,
} from './conversation-service'

interface ApiConversationListItemDTO {
  conversation_id: string
  title: string | null
  status: ConversationStatus
  channel: 'TEXT' | 'VOICE'
  teacher_role_id: string | null
  teacher_role?: Record<string, unknown> | null
  last_message_at: string | null
  updated_at: string
}

interface ApiConversationDTO extends ApiConversationListItemDTO {
  student_id: string
  current_page_context: Record<string, unknown> | null
  recent_messages: unknown[]
  conversation_summary: string | null
  created_at: string
}

interface ApiMessageDTO {
  message_id: string
  conversation_id: string
  role: Message['role']
  type: Message['type']
  content: string
  metadata?: Record<string, unknown> | null
  sequence: number
  model_info?: { provider: string; model: string } | null
  created_at: string
}

interface ApiConversationSummaryDTO {
  summary_id: string
  conversation_id: string
  summary: string
  token_count: number
  summary_version: number
  source_message_ids: string[]
  model_info: { provider: string; model: string } | null
  created_at: string
  updated_at: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function mapListItem(dto: ApiConversationListItemDTO): ConversationListItem {
  return {
    conversation_id: dto.conversation_id,
    title: dto.title,
    status: dto.status,
    channel: dto.channel,
    teacher_role_id: dto.teacher_role_id,
    teacher_role: dto.teacher_role ?? null,
    last_message_at: dto.last_message_at,
    updated_at: dto.updated_at,
  }
}

function mapMessage(dto: ApiMessageDTO): Message {
  return {
    message_id: dto.message_id,
    conversation_id: dto.conversation_id,
    role: dto.role,
    type: dto.type,
    content: dto.content,
    metadata: dto.metadata ?? {},
    sequence: dto.sequence,
    model_info: dto.model_info ?? null,
    created_at: dto.created_at,
  }
}

function mapConversation(dto: ApiConversationDTO): Conversation {
  return {
    ...mapListItem(dto),
    student_id: dto.student_id,
    current_page_context: dto.current_page_context ?? null,
    recent_messages: Array.isArray(dto.recent_messages)
      ? dto.recent_messages
          .filter(isRecord)
          .map((message) => mapMessage(message as unknown as ApiMessageDTO))
      : [],
    conversation_summary: dto.conversation_summary ?? null,
    created_at: dto.created_at,
  }
}

function mapSummary(dto: ApiConversationSummaryDTO): ConversationSummary {
  return {
    summary_id: dto.summary_id,
    conversation_id: dto.conversation_id,
    summary: dto.summary,
    token_count: dto.token_count,
    summary_version: dto.summary_version,
    source_message_ids: dto.source_message_ids,
    model_info: dto.model_info,
    updated_at: dto.updated_at,
  }
}

function queryString(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

function apiScreenContext(context: ScreenContext): Record<string, unknown> {
  const result: Record<string, unknown> = {
    route: context.route,
    page_type: context.pageType,
  }
  const optional: Array<[string, unknown]> = [
    ['book_id', context.bookId],
    ['chapter_id', context.chapterId],
    ['chapter_title', context.chapterTitle],
    ['content_block_id', context.contentBlockId],
    ['visible_section', context.visibleSection],
    ['selected_text', context.selectedText],
    ['knowledge_points', context.knowledgePoints],
    ['actions', context.actions],
  ]
  for (const [key, value] of optional) {
    if (value !== undefined) result[key] = value
  }
  return result
}

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `conv-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function isCallbacks(value: ScreenContext | SendMessageCallbacks | undefined): value is SendMessageCallbacks {
  return (
    isRecord(value) &&
    ('onStart' in value ||
      'onDelta' in value ||
      'onToolStart' in value ||
      'onToolResult' in value ||
      'onTextDone' in value ||
      'onDone' in value ||
      'onError' in value ||
      'signal' in value)
  )
}

function streamError(data: unknown): StreamErrorEvent {
  const value = isRecord(data) ? data : {}
  return {
    request_id: typeof value.request_id === 'string' ? value.request_id : undefined,
    code: typeof value.code === 'string' ? value.code : 'SSE_ERROR',
    message: typeof value.message === 'string' ? value.message : 'stream error',
    details: value.details,
    fatal: typeof value.fatal === 'boolean' ? value.fatal : true,
  }
}

export class ApiConversationService implements ConversationService {
  async getConversations(params?: ConversationListParams): Promise<ConversationListItem[]> {
    const payload = await apiRequest<ApiConversationListItemDTO[] | { items: ApiConversationListItemDTO[] }>(
      `/conversations${queryString({
        cursor: params?.cursor,
        limit: params?.limit,
        status: params?.status,
        channel: params?.channel,
      })}`,
    )
    const items = Array.isArray(payload) ? payload : payload.items
    return items.map(mapListItem)
  }

  async getConversation(conversationId: string): Promise<Conversation> {
    return mapConversation(
      await apiRequest<ApiConversationDTO>(`/conversations/${encodeURIComponent(conversationId)}`),
    )
  }

  async createConversation(input?: CreateConversationInput): Promise<Conversation> {
    return mapConversation(
      await apiRequest<ApiConversationDTO>('/conversations', {
        method: 'POST',
        body: input ?? {},
        headers: { 'Idempotency-Key': newIdempotencyKey() },
      }),
    )
  }

  async updateConversation(
    conversationId: string,
    patch: UpdateConversationInput,
  ): Promise<Conversation> {
    return mapConversation(
      await apiRequest<ApiConversationDTO>(`/conversations/${encodeURIComponent(conversationId)}`, {
        method: 'PATCH',
        body: patch,
      }),
    )
  }

  async getMessages(conversationId: string, params?: MessageListParams): Promise<Message[]> {
    const payload = await apiRequest<ApiMessageDTO[] | { items: ApiMessageDTO[] }>(
      `/conversations/${encodeURIComponent(conversationId)}/messages${queryString({
        cursor: params?.cursor,
        limit: params?.limit,
        sort: params?.sort,
      })}`,
    )
    const items = Array.isArray(payload) ? payload : payload.items
    return items.map(mapMessage)
  }

  async sendMessage(
    conversationId: string,
    input: SendMessageInput,
    callbacks?: SendMessageCallbacks,
  ): Promise<void>
  async sendMessage(
    conversationId: string,
    content: string,
    screenContext?: ScreenContext,
    callbacks?: SendMessageCallbacks,
  ): Promise<void>
  async sendMessage(
    conversationId: string,
    inputOrContent: SendMessageInput | string,
    screenContextOrCallbacks?: ScreenContext | SendMessageCallbacks,
    explicitCallbacks?: SendMessageCallbacks,
  ): Promise<void> {
    const input: SendMessageInput =
      typeof inputOrContent === 'string'
        ? {
            content: inputOrContent,
            screen_context: isCallbacks(screenContextOrCallbacks)
              ? undefined
              : screenContextOrCallbacks,
          }
        : inputOrContent
    const callbacks =
      typeof inputOrContent === 'string'
        ? isCallbacks(screenContextOrCallbacks)
          ? screenContextOrCallbacks
          : explicitCallbacks
        : isCallbacks(screenContextOrCallbacks)
          ? screenContextOrCallbacks
          : undefined
    const body: Record<string, unknown> = { content: input.content, type: 'TEXT' }
    if (input.screen_context) body.screen_context = apiScreenContext(input.screen_context)

    const options: FetchSSEOptions = {
      method: 'POST',
      body: JSON.stringify(body),
      signal: callbacks?.signal,
      onError: (error) => {
        callbacks?.onError?.(error instanceof Error ? error : new Error(String(error)))
      },
      onEvent: (eventType, data) => {
        switch (eventType) {
          case 'message.start':
            callbacks?.onStart?.(data as MessageStartEvent)
            break
          case 'text.delta':
            callbacks?.onDelta?.(data as TextDeltaEvent)
            break
          case 'tool.start':
            callbacks?.onToolStart?.(data as ToolStartEvent)
            break
          case 'tool.result':
            callbacks?.onToolResult?.(data as ToolResultEvent)
            break
          case 'text.done':
            callbacks?.onTextDone?.(data as TextDoneEvent)
            break
          case 'message.done':
            callbacks?.onDone?.(data as MessageDoneEvent)
            break
          case 'error':
            callbacks?.onError?.(streamError(data))
            break
          default:
            break
        }
      },
    }
    await fetchSSE(
      `${API_BASE}/conversations/${encodeURIComponent(conversationId)}/messages`,
      options,
    )
  }

  async getSummary(conversationId: string): Promise<ConversationSummary | null> {
    const payload = await apiRequest<ApiConversationSummaryDTO | null>(
      `/conversations/${encodeURIComponent(conversationId)}/summary`,
    )
    return payload ? mapSummary(payload) : null
  }
}
