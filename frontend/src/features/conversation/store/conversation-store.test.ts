import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SendMessageCallbacks } from '@/shared/api/conversation-service'

const mocks = vi.hoisted(() => ({
  conversationService: {
    getConversations: vi.fn(),
    getMessages: vi.fn(),
    createConversation: vi.fn(),
    sendMessage: vi.fn(),
  },
  quizService: { createQuizSession: vi.fn() },
  setAiState: vi.fn(),
}))

vi.mock('@/mocks/services', () => mocks)
vi.mock('@/features/companion', () => ({
  useCompanionStore: { getState: () => ({ setAiState: mocks.setAiState }) },
}))

import { useConversationStore } from './conversation-store'

const conversation = {
  conversation_id: 'conversation-1',
  title: '课程对话',
  status: 'ACTIVE' as const,
  channel: 'TEXT' as const,
  teacher_role_id: null,
  teacher_role: null,
  last_message_at: null,
  updated_at: '2026-08-19T08:00:00Z',
}

describe('conversation store real service lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.getState().abortCurrent()
    useConversationStore.setState({ messages: [], conversationId: null, loaded: false })
    mocks.conversationService.getConversations.mockResolvedValue([])
    mocks.conversationService.getMessages.mockResolvedValue([])
    mocks.conversationService.createConversation.mockResolvedValue({
      ...conversation,
      student_id: 'student-1',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T08:00:00Z',
    })
  })

  it('首发消息前自动创建会话，并聚合 SSE start/delta/done', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onStart?.({
          message_id: 'teacher-1',
          conversation_id: 'conversation-1',
          role: 'TEACHER',
          type: 'TEXT',
          sequence: 2,
        })
        callbacks?.onDelta?.({ message_id: 'teacher-1', delta: '训练' })
        callbacks?.onDelta?.({ message_id: 'teacher-1', delta: '数据' })
        callbacks?.onDone?.({
          message_id: 'teacher-1',
          conversation_id: 'conversation-1',
          sequence: 2,
        })
      },
    )

    await useConversationStore.getState().send('解释训练数据')

    expect(mocks.conversationService.createConversation).toHaveBeenCalledWith({ channel: 'TEXT' })
    expect(mocks.conversationService.sendMessage).toHaveBeenCalledWith(
      'conversation-1',
      { content: '解释训练数据' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '解释训练数据' }),
      expect.objectContaining({ id: 'teacher-1', role: 'ai', content: '训练数据', streaming: false }),
    ])
  })

  it('打开面板时选择已有 ACTIVE 会话并加载历史消息', async () => {
    mocks.conversationService.getConversations.mockResolvedValue([conversation])
    mocks.conversationService.getMessages.mockResolvedValue([
      {
        message_id: 'message-1',
        conversation_id: 'conversation-1',
        role: 'TEACHER',
        type: 'TEXT',
        content: '历史回复',
        metadata: {},
        sequence: 1,
        model_info: null,
        created_at: '2026-08-19T08:00:00Z',
      },
    ])

    await useConversationStore.getState().load()

    expect(mocks.conversationService.getMessages).toHaveBeenCalledWith(
      'conversation-1',
      { sort: 'asc' },
    )
    expect(useConversationStore.getState()).toMatchObject({
      conversationId: 'conversation-1',
      loaded: true,
      messages: [expect.objectContaining({ content: '历史回复', role: 'ai' })],
    })
  })
})
