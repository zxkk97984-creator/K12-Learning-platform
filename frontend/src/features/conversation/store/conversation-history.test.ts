// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getConversations: vi.fn(),
  createConversation: vi.fn(),
  getMessages: vi.fn(),
  updateConversation: vi.fn(),
  getConversation: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
  conversationService: {
    getConversations: mocks.getConversations,
    createConversation: mocks.createConversation,
    getMessages: mocks.getMessages,
    updateConversation: mocks.updateConversation,
    getConversation: mocks.getConversation,
    sendMessage: vi.fn(),
  },
}))
vi.mock('@/features/companion', () => ({
  useCompanionStore: Object.assign((selector: (state: unknown) => unknown) => selector({}), {
    getState: () => ({ setAiState: vi.fn() }),
  }),
  currentTeacherName: () => '霜铃',
  useTeacherName: () => '霜铃',
}))

import { useConversationStore } from './conversation-store'

function conv(id: string, status: 'ACTIVE' | 'ARCHIVED', updated_at: string) {
  return {
    conversation_id: id,
    title: null,
    status,
    channel: 'TEXT',
    teacher_role_id: null,
    teacher_role: { name: '温暖鼓励' },
    last_message_preview: `预览-${id}`,
    last_message_at: updated_at,
    updated_at,
  }
}

describe('conversation history（Phase 4 对话历史持久化）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    useConversationStore.setState({
      messages: [],
      conversationId: null,
      loaded: false,
      history: [],
      historyLoaded: false,
      lastScreenContext: null,
    })
  })

  it('loadHistory 合并 ACTIVE 与 ARCHIVED 并按更新时间倒序', async () => {
    mocks.getConversations.mockImplementation(async ({ status }) =>
      status === 'ACTIVE'
        ? [conv('a1', 'ACTIVE', '2026-08-24T10:00:00Z')]
        : [conv('h1', 'ARCHIVED', '2026-08-24T12:00:00Z'), conv('h2', 'ARCHIVED', '2026-08-23T09:00:00Z')],
    )

    await useConversationStore.getState().loadHistory()
    const history = useConversationStore.getState().history
    expect(history.map((entry) => entry.id)).toEqual(['h1', 'a1', 'h2'])
    expect(history[0].teacher_role_name).toBe('温暖鼓励')
    expect(history[0].last_message_preview).toBe('预览-h1')
  })

  it('switchConversation 拉取消息并写入 localStorage', async () => {
    mocks.getMessages.mockResolvedValue([
      {
        message_id: 'm1',
        conversation_id: 'target',
        role: 'STUDENT',
        type: 'TEXT',
        content: '你好',
        metadata: {},
        sequence: 1,
        model_info: {},
        created_at: '2026-08-24T10:00:00Z',
      },
    ])

    await useConversationStore.getState().switchConversation('target')

    expect(useConversationStore.getState().conversationId).toBe('target')
    expect(window.localStorage.getItem('shuangling-active-conversation')).toBe('target')
    expect(useConversationStore.getState().messages[0].content).toBe('你好')
  })

  it('归档当前会话后自动切换到最新 ACTIVE 会话', async () => {
    useConversationStore.setState({ conversationId: 'current' })
    mocks.updateConversation.mockResolvedValue({})
    mocks.getConversations.mockImplementation(async ({ status }) =>
      status === 'ACTIVE' ? [conv('other-active', 'ACTIVE', '2026-08-24T11:00:00Z')] : [],
    )
    mocks.getMessages.mockResolvedValue([])

    await useConversationStore.getState().setConversationStatus('current', 'ARCHIVED')

    expect(mocks.updateConversation).toHaveBeenCalledWith('current', { status: 'ARCHIVED' })
    expect(useConversationStore.getState().conversationId).toBe('other-active')
  })

  it('归档唯一会话后自动新建并切换到新会话', async () => {
    useConversationStore.setState({ conversationId: 'solo' })
    mocks.updateConversation.mockResolvedValue({})
    // 第一次 loadHistory（归档后）无 ACTIVE；startNewConversation 创建
    mocks.getConversations.mockResolvedValue([])
    mocks.createConversation.mockResolvedValue({
      conversation_id: 'fresh',
      student_id: 's',
      teacher_role_id: null,
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '',
      updated_at: '2026-08-24T12:00:00Z',
      last_message_at: null,
    })
    mocks.getMessages.mockResolvedValue([])

    await useConversationStore.getState().setConversationStatus('solo', 'ARCHIVED')

    expect(mocks.createConversation).toHaveBeenCalled()
    expect(useConversationStore.getState().conversationId).toBe('fresh')
  })

  it('软删除唯一会话后：历史不含 DELETED，且自动新建并切换到新会话', async () => {
    mocks.getConversations.mockResolvedValue([])
    mocks.createConversation.mockResolvedValue({
      conversation_id: 'fresh-after-delete',
      student_id: 's',
      teacher_role_id: null,
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '',
      updated_at: '2026-08-24T12:00:00Z',
      last_message_at: null,
    })
    mocks.getMessages.mockResolvedValue([])
    useConversationStore.setState({ conversationId: 'solo-del' })

    await useConversationStore.getState().setConversationStatus('solo-del', 'DELETED')

    const history = useConversationStore.getState().history
    expect(history.every((entry) => entry.status !== 'DELETED')).toBe(true)
    expect(useConversationStore.getState().conversationId).toBe('fresh-after-delete')
    expect(mocks.createConversation).toHaveBeenCalledTimes(1)
  })
})
