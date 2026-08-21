// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  messages: [] as Array<Record<string, unknown>>,
  retry: vi.fn(),
  setOpen: vi.fn(),
  setAiState: vi.fn(),
}))

vi.mock('../store/conversation-store', () => ({
  useConversationStore: (selector: (state: unknown) => unknown) =>
    selector({ messages: mocks.messages, retry: mocks.retry }),
}))

vi.mock('@/features/companion', () => ({
  useCompanionStore: { getState: () => ({ setOpen: mocks.setOpen, setAiState: mocks.setAiState }) },
}))

vi.mock('@/features/quiz', () => ({
  QuizCard: () => null,
}))

import { MessageList } from './MessageList'

describe('MessageList error rendering', () => {
  beforeEach(() => {
    mocks.messages = [
      {
        id: 'error-1',
        role: 'ai',
        kind: 'error',
        content: 'AI 没有返回有效内容，请重试（AI_EMPTY_RESPONSE）',
      },
    ]
    vi.clearAllMocks()
  })

  it('preserves underscores in provider error codes', () => {
    render(<MessageList />)

    expect(screen.getByText('AI 没有返回有效内容，请重试（AI_EMPTY_RESPONSE）')).toBeTruthy()
  })
})
