// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { VoiceClientCallbacks } from '@/shared/api/voice-client'

const mocks = vi.hoisted(() => ({
  setAiState: vi.fn(),
  showToast: vi.fn(),
  createVoiceClient: vi.fn(),
  callbacks: null as VoiceClientCallbacks | null,
  getConversations: vi.fn(),
  createConversation: vi.fn(),
  getMessages: vi.fn(),
}))

vi.mock('@/features/companion', () => ({
  useCompanionStore: (selector: (state: unknown) => unknown) =>
    selector({ setAiState: mocks.setAiState }),
}))

vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (state: unknown) => unknown) =>
    selector({ showToast: mocks.showToast }),
}))

vi.mock('@/features/screen-context', () => ({
  useScreenContext: () => ({ screenContext: { route: '/home', pageType: 'home' } }),
}))

vi.mock('@/shared/api/voice-client', () => ({
  createVoiceClient: (options: { callbacks: VoiceClientCallbacks }) => {
    mocks.callbacks = options.callbacks
    return mocks.createVoiceClient(options)
  },
}))

vi.mock('@/mocks/services', () => ({
  conversationService: {
    getConversations: mocks.getConversations,
    createConversation: mocks.createConversation,
    getMessages: mocks.getMessages,
  },
}))

import { useConversationStore } from '../store/conversation-store'
import { ChatComposer } from './ChatComposer'

describe('ChatComposer voice UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState({ messages: [], conversationId: null, loaded: false })
    mocks.getConversations.mockResolvedValue([])
    mocks.createConversation.mockResolvedValue({
      conversation_id: 'conversation-voice',
      student_id: 'student-1',
      teacher_role_id: null,
      title: null,
      status: 'ACTIVE',
      channel: 'TEXT',
      current_page_context: {},
      recent_messages: [],
      conversation_summary: null,
      created_at: '2026-08-19T00:00:00Z',
      updated_at: '2026-08-19T00:00:00Z',
      last_message_at: null,
    })
    mocks.getMessages.mockResolvedValue([])
    mocks.createVoiceClient.mockReturnValue({
      connect: vi.fn().mockResolvedValue(undefined),
      sendAudioChunk: vi.fn(),
      sendAudioEnd: vi.fn(),
      cancel: vi.fn(),
      ping: vi.fn(),
      close: vi.fn(),
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('渲染麦克风按钮', () => {
    render(React.createElement(ChatComposer))
    expect(screen.getByRole('button', { name: '语音输入' })).toBeTruthy()
  })

  it('无麦克风权限时降级为文字输入并显示错误状态', async () => {
    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.showToast).toHaveBeenCalledWith('语音不可用，请使用文字输入'))
    expect(screen.getByText('语音暂时不可用，请使用文字输入')).toBeTruthy()
  })

  it('收到 SPEAKING 状态后显示说话徽标并同步桌宠', async () => {
    render(React.createElement(ChatComposer))
    fireEvent.click(screen.getByRole('button', { name: '语音输入' }))

    await waitFor(() => expect(mocks.callbacks).not.toBeNull())
    act(() => mocks.callbacks?.onState?.('SPEAKING'))

    expect(screen.getByText('正在说话…')).toBeTruthy()
    expect(mocks.setAiState).toHaveBeenCalledWith('speaking')
  })
})
