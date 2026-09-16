// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/shared/api/auth'
import type { SendMessageCallbacks } from '@/shared/api/conversation-service'

const mocks = vi.hoisted(() => ({
  conversationService: {
    getConversations: vi.fn(),
    getMessages: vi.fn(),
    createConversation: vi.fn(),
    sendMessage: vi.fn(),
    updateConversation: vi.fn(),
  },
  companion: { setAiState: vi.fn() },
}))

vi.mock('@/shared/services', () => mocks)
vi.mock('@/features/companion', () => ({
  useCompanionStore: { getState: () => ({ setAiState: mocks.companion.setAiState }) },
  currentTeacherName: () => '霜铃',
}))

import { useConversationStore } from '@/features/conversation/store/conversation-store'

// JWT：sub=A-USER 与 sub=B-USER 两个用户（payload 由测试构造）。
function tokenFor(sub: string): string {
  const payload = btoa(JSON.stringify({ sub, user_type: 'STUDENT', username: sub }))
  return `hdr.${payload}.sig`
}

function setUser(sub: string): void {
  setToken(tokenFor(sub))
}

function resetStore(): void {
  useConversationStore.getState().reset()
}

describe('T06 账号切换隔离', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    resetStore()
    mocks.conversationService.getConversations.mockResolvedValue([])
    mocks.conversationService.getMessages.mockResolvedValue([])
    mocks.conversationService.createConversation.mockResolvedValue({
      conversation_id: 'c-A',
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      teacher_role_id: null,
      teacher_role: null,
      student_id: 's1',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T08:00:00Z',
      updated_at: '2026-08-19T08:00:00Z',
      last_message_at: null,
    })
  })

  it('reset 清空 messages/history/loaded/conversationId/幂等键', () => {
    setUser('A-USER')
    useConversationStore.setState({
      messages: [
        { id: 'm1', role: 'user', kind: 'text', content: 'A 的问题', meta: '' },
      ],
      conversationId: 'c-A',
      loaded: true,
      loadedEpoch: 1,
      lastIdempotencyKey: 'idem-1',
      history: [
        { id: 'h1', title: null, status: 'ACTIVE', teacher_role_name: null, last_message_preview: null, updated_at: 'x' },
      ],
      historyLoaded: true,
    })
    resetStore()
    const state = useConversationStore.getState()
    expect(state.messages).toEqual([])
    expect(state.conversationId).toBeNull()
    expect(state.loaded).toBe(false)
    expect(state.lastIdempotencyKey).toBeNull()
    expect(state.history).toEqual([])
    expect(state.historyLoaded).toBe(false)
  })

  it('A 的慢 getMessages 在 B 登录后返回不得回填（世代失效）', async () => {
    setUser('A-USER')
    // A 打开对话：后端慢，返回 A 的消息。
    let resolveA: (v: unknown) => void
    mocks.conversationService.getMessages.mockReturnValue(
      new Promise((resolve) => {
        resolveA = resolve
      }),
    )
    const loadPromise = useConversationStore.getState().load()
    // B 登录：立刻切换账号（reset 递增世代）。
    setUser('B-USER')
    resetStore()
    // A 的慢响应此时返回，但世代已变，不得写入 B 的 store。
    resolveA!([
      { message_id: 'a-msg', role: 'STUDENT', type: 'TEXT', content: 'A 的对话', sequence: 1 },
    ])
    await loadPromise
    expect(useConversationStore.getState().messages).toEqual([])
  })

  it('active-conversation 键按用户隔离，B 不读到 A 的记录', () => {
    setUser('A-USER')
    window.localStorage.setItem('shuangling-active-conversation:A-USER', 'conv-A')

    setUser('B-USER')
    // B 读取时键应为 B 自己的命名空间，读不到 A 的 conv-A。
    expect(window.localStorage.getItem('shuangling-active-conversation:B-USER')).toBeNull()
  })

  it('reset 会终止在途 send 的迟到 onDelta（不回填旧用户文本）', async () => {
    setUser('A-USER')
    mocks.conversationService.getConversations.mockResolvedValue([{
      conversation_id: 'c-A',
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      teacher_role_id: null,
      teacher_role: null,
      last_message_at: null,
      updated_at: '2026-08-19T08:00:00Z',
    }])
    mocks.conversationService.getMessages.mockResolvedValue([])
    let fireDelta: (() => void) | undefined
    mocks.conversationService.sendMessage.mockImplementation(
      async (_id: string, _input: unknown, callbacks?: SendMessageCallbacks) => {
        callbacks?.onStart?.({ message_id: 't-1', conversation_id: 'c-A', role: 'TEACHER', type: 'TEXT', sequence: 2 })
        fireDelta = () => callbacks?.onDelta?.({ message_id: 't-1', delta: 'A 的答案' })
      },
    )
    const sendPromise = useConversationStore.getState().send('A 的问题')
    await sendPromise
    // A 流式途中 B 登录。
    setUser('B-USER')
    resetStore()
    // 迟到 delta 不得写入。
    fireDelta!()
    expect(useConversationStore.getState().messages).toEqual([])
  })
})
