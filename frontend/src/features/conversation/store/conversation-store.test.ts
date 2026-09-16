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

vi.mock('@/shared/services', () => mocks)
vi.mock('@/features/companion', () => ({
  useCompanionStore: { getState: () => ({ setAiState: mocks.setAiState }) },
  currentTeacherName: () => '霜铃',
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
      expect.any(String),
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

  it('收到 SSE error callback 时追加 error 类型消息', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onError?.({
          code: 'AI_PROVIDER_ERROR',
          message: 'AI provider unavailable',
          fatal: true,
        })
      },
    )

    await useConversationStore.getState().send('触发错误事件')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({
        role: 'user',
        content: '触发错误事件',
      }),
      expect.objectContaining({
        role: 'ai',
        kind: 'error',
        content: expect.stringContaining('AI provider unavailable'),
      }),
    ])
  })

  it('收到 text.done 后以最终正文结束流式消息', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onStart?.({
          message_id: 'teacher-done',
          conversation_id: 'conversation-1',
          role: 'TEACHER',
          type: 'TEXT',
          sequence: 2,
        })
        callbacks?.onTextDone?.({
          message_id: 'teacher-done',
          content: '最终完整答案',
        })
        callbacks?.onDone?.({
          message_id: 'teacher-done',
          conversation_id: 'conversation-1',
          sequence: 2,
        })
      },
    )

    await useConversationStore.getState().send('只发送最终正文')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '只发送最终正文' }),
      expect.objectContaining({
        id: 'teacher-done',
        role: 'ai',
        kind: 'text',
        content: '最终完整答案',
        streaming: false,
      }),
    ])
  })

  it('发送请求被拒绝时也显示 error 类型消息', async () => {
    mocks.conversationService.sendMessage.mockRejectedValue(
      new Error('stream disconnected'),
    )

    await useConversationStore.getState().send('触发断流')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '触发断流' }),
      expect.objectContaining({
        role: 'ai',
        kind: 'error',
        content: 'stream disconnected',
      }),
    ])
  })

  it('quiz tool 事件：tool.start 显示生成中，tool.result 渲染真实 QuizCard', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onStart?.({
          message_id: 'teacher-1',
          conversation_id: 'conversation-1',
          role: 'TEACHER',
          type: 'TEXT',
          sequence: 2,
        })
        callbacks?.onToolStart?.({
          tool_run_id: 'tool-run-1',
          tool: 'quiz',
          state: 'running',
          payload: { quiz_session_id: null },
        })
        callbacks?.onToolResult?.({
          tool_run_id: 'tool-run-1',
          tool: 'quiz',
          status: 'success',
          payload: { quiz_session_id: 'quiz-uuid-1', skill_version: 'quiz-v1' },
        })
        callbacks?.onDone?.({
          message_id: 'teacher-1',
          conversation_id: 'conversation-1',
          sequence: 2,
        })
      },
    )

    await useConversationStore.getState().send('给我出题')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '给我出题' }),
      expect.objectContaining({
        id: 'tool-tool-run-1',
        role: 'ai',
        kind: 'quiz',
        content: '测验已创建 · 正式测验已记录',
        quiz: { sessionId: 'quiz-uuid-1' },
      }),
    ])
  })

  it('「给我出题」只发送文本，不再触发 Mock 的 createQuizSession', async () => {
    mocks.conversationService.sendMessage.mockResolvedValue(undefined)

    useConversationStore.getState().runIntent('quiz')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mocks.conversationService.sendMessage).toHaveBeenCalledWith(
      'conversation-1',
      { content: '给我出题' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
      expect.any(String),
    )
    expect(mocks.quizService.createQuizSession).not.toHaveBeenCalled()
  })

  it('历史加载时把带 quiz 元数据的 TEXT 消息还原为 QuizCard', async () => {
    mocks.conversationService.getConversations.mockResolvedValue([conversation])
    mocks.conversationService.getMessages.mockResolvedValue([
      {
        message_id: 'message-quiz-1',
        conversation_id: 'conversation-1',
        role: 'TEACHER',
        type: 'TEXT',
        content: '好的，我来出一道题，请听题～',
        metadata: { tool: 'quiz', quiz_session_id: 'quiz-uuid-1' },
        sequence: 2,
        model_info: { provider: 'quiz-bank', model: 'quiz-bank-v1' },
        created_at: '2026-08-19T08:00:00Z',
      },
      {
        message_id: 'message-empty-teacher',
        conversation_id: 'conversation-1',
        role: 'TEACHER',
        type: 'TEXT',
        content: '',
        metadata: {},
        sequence: 3,
        model_info: null,
        created_at: '2026-08-19T08:00:01Z',
      },
    ])

    await useConversationStore.getState().load()

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({
        kind: 'quiz',
        content: '好的，我来出一道题，请听题～',
        quiz: { sessionId: 'quiz-uuid-1' },
      }),
    ])
  })

  it('quiz tool.result 失败时渲染错误状态，不渲染 QuizCard', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onToolStart?.({
          tool_run_id: 'tool-run-error',
          tool: 'quiz',
          state: 'running',
          payload: { quiz_session_id: null },
        })
        callbacks?.onToolResult?.({
          tool_run_id: 'tool-run-error',
          tool: 'quiz',
          status: 'error',
          payload: { error: 'generation failed' },
        })
        callbacks?.onDone?.({
          message_id: 'teacher-error',
          conversation_id: 'conversation-1',
          sequence: 2,
        })
      },
    )

    await useConversationStore.getState().send('给我出题')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '给我出题' }),
      expect.objectContaining({
        id: 'tool-tool-run-error',
        role: 'ai',
        kind: 'tool',
        content: '测验生成失败，请稍后再试',
        quiz: null,
      }),
    ])
  })

  it('SSE 在 start 后报错时移除空的 AI 气泡', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onStart?.({
          message_id: 'teacher-empty-error',
          conversation_id: 'conversation-1',
          role: 'TEACHER',
          type: 'TEXT',
          sequence: 2,
        })
        callbacks?.onError?.({
          code: 'AI_EMPTY_RESPONSE',
          message: 'AI 没有返回有效内容，请重试',
          fatal: true,
        })
      },
    )

    await useConversationStore.getState().send('触发空回复')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '触发空回复' }),
      expect.objectContaining({ role: 'ai', kind: 'error' }),
    ])
    expect(useConversationStore.getState().messages).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'teacher-empty-error', role: 'ai', content: '' }),
      ]),
    )
  })

  it('非 quiz 工具沿用通用 TOOL_STATUS 文案', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onToolStart?.({
          tool_run_id: 'tool-run-hint',
          tool: 'hint',
          state: 'running',
          payload: {},
        })
        callbacks?.onToolResult?.({
          tool_run_id: 'tool-run-hint',
          tool: 'hint',
          status: 'success',
          payload: { hint_level: 1 },
        })
        callbacks?.onDone?.({
          message_id: 'teacher-hint',
          conversation_id: 'conversation-1',
          sequence: 2,
        })
      },
    )

    await useConversationStore.getState().send('给我一点提示')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '给我一点提示' }),
      expect.objectContaining({
        id: 'tool-tool-run-hint',
        role: 'ai',
        kind: 'tool',
        content: 'hint · 已完成',
      }),
    ])
  })

  it('quiz tool.result 缺 quiz_session_id 时保持 tool 状态', async () => {
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onToolStart?.({
          tool_run_id: 'tool-run-empty',
          tool: 'quiz',
          state: 'running',
          payload: { quiz_session_id: null },
        })
        callbacks?.onToolResult?.({
          tool_run_id: 'tool-run-empty',
          tool: 'quiz',
          status: 'success',
          payload: {},
        })
        callbacks?.onDone?.({
          message_id: 'teacher-empty',
          conversation_id: 'conversation-1',
          sequence: 2,
        })
      },
    )

    await useConversationStore.getState().send('给我出题')

    expect(useConversationStore.getState().messages).toEqual([
      expect.objectContaining({ role: 'user', content: '给我出题' }),
      expect.objectContaining({
        id: 'tool-tool-run-empty',
        role: 'ai',
        kind: 'quiz',
        content: '测验已创建 · 正式测验已记录',
        quiz: null,
      }),
    ])
  })
})

describe('conversation store screen-context passing (Phase 2-A)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.getState().abortCurrent()
    useConversationStore.setState({
      messages: [],
      conversationId: null,
      loaded: false,
      lastScreenContext: null,
    })
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

  const readerContext = {
    route: '/learn/b1/c1',
    pageType: 'chapter_reader',
    bookId: 'b1',
    chapterId: 'c1',
    chapterTitle: '训练数据',
  }

  it('runIntent 把当前 ScreenContext 随消息发送（quiz intent 同样携带）', async () => {
    mocks.conversationService.sendMessage.mockResolvedValue(undefined)

    await new Promise<void>((resolve) => {
      mocks.conversationService.sendMessage.mockImplementation(
        async (_id: string, input: { screen_context?: unknown }, callbacks?: SendMessageCallbacks) => {
          callbacks?.onDone?.({ message_id: 'm-ctx', conversation_id: 'conversation-1', sequence: 2 })
          resolve()
          expect(input.screen_context).toEqual(readerContext)
        },
      )
      useConversationStore.getState().runIntent('explain', undefined, readerContext)
    })

    const input = mocks.conversationService.sendMessage.mock.calls[0][1] as {
      screen_context?: unknown
    }
    expect(input.screen_context).toEqual(readerContext)
    // 最后一次真实上下文已保存
    expect(useConversationStore.getState().lastScreenContext).toEqual(readerContext)
  })

  it('retry 复用最后一次真实上下文', async () => {
    mocks.conversationService.sendMessage.mockImplementation(async (_id, _input, callbacks) => {
      callbacks?.onDone?.({ message_id: 'm-retry', conversation_id: 'conversation-1', sequence: 2 })
    })

    await useConversationStore.getState().send('解释我选中的内容', readerContext)
    await useConversationStore.getState().retry()

    const retryCall = mocks.conversationService.sendMessage.mock.calls.at(-1)!
    const input = retryCall[1] as { screen_context?: unknown; content: string }
    expect(input.content).toBe('解释我选中的内容')
    expect(input.screen_context).toEqual(readerContext)

    // Phase 5-A 整改 2：retry 的第四个参数（幂等键）必须与首次 send 相同且非空
    const firstCall = mocks.conversationService.sendMessage.mock.calls[0]
    const firstKey = firstCall[3] as string | undefined
    expect(typeof firstKey).toBe('string')
    expect((firstKey as string).length).toBeGreaterThan(0)
    const retryKey = retryCall[3] as string | undefined
    expect(retryKey).toBe(firstKey)
  })
})
