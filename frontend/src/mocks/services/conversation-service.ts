import type { ConversationService } from '@/shared/api/conversation-service'
import type {
  CreateConversationInput,
  SendMessageCallbacks,
  SendMessageInput,
  UpdateConversationInput,
} from '@/shared/api/conversation-service'
import type { Conversation, ConversationSummary, Message } from '@/entities/conversation/types'
import type { ScreenContext } from '@/features/screen-context/types'

import { delay } from '../delay'
import { mockConversation, mockMessages } from '../data/conversation'

let messages: Message[] = mockMessages.map((message) => ({ ...message }))
let conversations: Conversation[] = [
  { ...mockConversation, recent_messages: messages.map((message) => ({ ...message })) },
]
let conversationSeq = 2

function isCallbacks(
  value: ScreenContext | SendMessageCallbacks | undefined,
): value is SendMessageCallbacks {
  return Boolean(
    value &&
      ('onStart' in value ||
        'onDelta' in value ||
        'onToolStart' in value ||
        'onToolResult' in value ||
        'onTextDone' in value ||
        'onDone' in value ||
        'onError' in value ||
        'signal' in value),
  )
}

function storedScreenContext(context: ScreenContext): Record<string, unknown> {
  return {
    route: context.route,
    page_type: context.pageType,
    ...(context.bookId ? { book_id: context.bookId } : {}),
    ...(context.chapterId ? { chapter_id: context.chapterId } : {}),
    ...(context.chapterTitle ? { chapter_title: context.chapterTitle } : {}),
    ...(context.contentBlockId ? { content_block_id: context.contentBlockId } : {}),
    ...(context.visibleSection ? { visible_section: context.visibleSection } : {}),
    ...(context.selectedText ? { selected_text: context.selectedText } : {}),
    ...(context.knowledgePoints ? { knowledge_points: context.knowledgePoints } : {}),
    ...(context.actions ? { actions: context.actions } : {}),
  }
}

function replyFor(content: string): string {
  if (content.includes('为什么')) {
    return '因为当前这节内容会影响机器之后看到的新情况。它学到的不是“永远正确的答案”，而是从例子里归纳出来的规律，所以例子不完整时，判断也会变窄。'
  }
  return '我会把你的问题和当前这节内容连起来回答：先把训练数据理解成“机器看过的例子”，再看这些例子怎样影响它的判断。要不要我换成一个更贴近生活的例子？'
}

export class MockConversationService implements ConversationService {
  async getConversations() {
    return delay(
      conversations.map((conversation) => ({
        conversation_id: conversation.conversation_id,
        title: conversation.title,
        status: conversation.status,
        channel: conversation.channel,
        teacher_role_id: conversation.teacher_role_id,
        teacher_role: null,
        last_message_at: conversation.last_message_at,
        updated_at: conversation.updated_at,
      })),
      200,
    )
  }

  async getConversation(conversationId: string) {
    const conversation = conversations.find((item) => item.conversation_id === conversationId)
    if (!conversation) throw new Error(`CONVERSATION_NOT_FOUND: ${conversationId}`)
    return delay(
      {
        ...conversation,
        recent_messages: messages.filter((message) => message.conversation_id === conversationId),
      },
      200,
    )
  }

  async createConversation(input?: CreateConversationInput) {
    const now = new Date().toISOString()
    const conversation: Conversation = {
      conversation_id: `conv-new-${conversationSeq}`,
      student_id: 'stu-xiaoming',
      teacher_role_id: input?.teacher_role_id ?? 'role-shuangling',
      title: input?.title ?? '新对话',
      status: 'ACTIVE',
      channel: input?.channel ?? 'TEXT',
      current_page_context: null,
      recent_messages: [],
      conversation_summary: null,
      created_at: now,
      updated_at: now,
      last_message_at: null,
    }
    conversationSeq += 1
    conversations = [...conversations, conversation]
    return delay(conversation, 200)
  }

  async updateConversation(conversationId: string, patch: UpdateConversationInput) {
    const conversation = conversations.find((item) => item.conversation_id === conversationId)
    if (!conversation) throw new Error(`CONVERSATION_NOT_FOUND: ${conversationId}`)
    const updated: Conversation = {
      ...conversation,
      ...patch,
      updated_at: new Date().toISOString(),
    }
    conversations = conversations.map((item) =>
      item.conversation_id === conversationId ? updated : item,
    )
    return delay(updated, 200)
  }

  async getMessages(conversationId: string) {
    return delay(
      messages.filter((message) => message.conversation_id === conversationId),
      200,
    )
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
            screen_context:
              screenContextOrCallbacks && 'route' in screenContextOrCallbacks
                ? screenContextOrCallbacks
                : undefined,
          }
        : inputOrContent
    const callbacks: SendMessageCallbacks | undefined =
      typeof inputOrContent === 'string'
        ? screenContextOrCallbacks && 'route' in screenContextOrCallbacks
          ? explicitCallbacks
          : isCallbacks(screenContextOrCallbacks)
            ? screenContextOrCallbacks
            : undefined
        : isCallbacks(screenContextOrCallbacks)
          ? screenContextOrCallbacks
          : undefined

    const conversation = conversations.find((item) => item.conversation_id === conversationId)
    if (!conversation) throw new Error(`CONVERSATION_NOT_FOUND: ${conversationId}`)

    const baseSequence = messages.filter(
      (message) => message.conversation_id === conversationId,
    ).length
    const now = new Date().toISOString()
    const userMessage: Message = {
      message_id: `msg-${conversationId}-${baseSequence + 1}`,
      conversation_id: conversationId,
      role: 'STUDENT',
      type: 'TEXT',
      content: input.content,
      metadata: {},
      sequence: baseSequence + 1,
      model_info: null,
      created_at: now,
    }
    const assistantMessage: Message = {
      message_id: `msg-${conversationId}-${baseSequence + 2}`,
      conversation_id: conversationId,
      role: 'TEACHER',
      type: 'TEXT',
      content: replyFor(input.content),
      metadata: {},
      sequence: baseSequence + 2,
      model_info: { provider: 'mock', model: 'mock-model' },
      created_at: new Date(Date.now() + 300).toISOString(),
    }
    messages = [...messages, userMessage, assistantMessage]
    conversations = conversations.map((item) =>
      item.conversation_id === conversationId
        ? {
            ...item,
            current_page_context: input.screen_context
              ? storedScreenContext(input.screen_context)
              : item.current_page_context,
            last_message_at: assistantMessage.created_at,
            updated_at: assistantMessage.created_at,
          }
        : item,
    )
    await delay(undefined, 250)
    callbacks?.onStart?.({
      message_id: assistantMessage.message_id,
      conversation_id: conversationId,
      role: 'TEACHER',
      type: 'TEXT',
      sequence: assistantMessage.sequence,
      created_at: assistantMessage.created_at,
      request_id: `mock-${assistantMessage.message_id}`,
    })
    callbacks?.onDelta?.({
      message_id: assistantMessage.message_id,
      delta: assistantMessage.content,
      index: 0,
      sequence: assistantMessage.sequence,
    })
    callbacks?.onTextDone?.({
      message_id: assistantMessage.message_id,
      content: assistantMessage.content,
      model_info: assistantMessage.model_info,
    })
    callbacks?.onDone?.({
      message_id: assistantMessage.message_id,
      conversation_id: conversationId,
      sequence: assistantMessage.sequence,
      created_at: assistantMessage.created_at,
      metadata: {},
    })
  }

  async getSummary(_conversationId: string) {
    // 原型无摘要数据；长会话摘要由 Worker 生成（0-C）
    return delay(null as ConversationSummary | null, 150)
  }
}
