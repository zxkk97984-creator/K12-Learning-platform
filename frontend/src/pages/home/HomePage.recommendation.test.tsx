// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Recommendation } from '@/shared/api/recommendation-service'

const mocks = vi.hoisted(() => ({
  getMe: vi.fn(),
  getProgress: vi.fn(),
  getBook: vi.fn(),
  getChapter: vi.fn(),
  getEpisodes: vi.fn(),
  getMemories: vi.fn(),
  getQuizSessions: vi.fn(),
  getRecommendations: vi.fn(),
}))

vi.mock('@/mocks/services', () => ({
  studentService: { getMe: mocks.getMe },
  contentService: {
    getProgress: mocks.getProgress,
    getBook: mocks.getBook,
    getChapter: mocks.getChapter,
  },
  memoryService: {
    getEpisodes: mocks.getEpisodes,
    getMemories: mocks.getMemories,
  },
  quizService: { getQuizSessions: mocks.getQuizSessions },
  recommendationService: { getRecommendations: mocks.getRecommendations },
}))

vi.mock('@/features/companion', () => ({
  CompanionSprite: () => <span aria-hidden="true" />,
  useCompanionStore: { getState: () => ({ setOpen: vi.fn() }) },
}))

vi.mock('@/features/conversation', () => ({
  useConversationStore: (selector: (state: { runIntent: () => void }) => unknown) =>
    selector({ runIntent: vi.fn() }),
}))

import HomePage from './HomePage'

const recommendation: Recommendation = {
  recommendation_id: 'recommendation-1',
  recommendation_type: 'REVIEW_WEAK',
  title: '复习《科学实验》的关键概念',
  description: '用一小段复习把最近测验中不稳的概念重新连起来。',
  reason: '最近 3 次相关测验的正确率约为 33%，先复习再继续挑战。',
  evidence_ids: ['answer-1', 'answer-2'],
  related_book_id: 'book-1',
  status: 'ACTIVE',
  created_at: '2026-08-21T10:00:00Z',
  updated_at: '2026-08-21T10:00:00Z',
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="home-location">{location.pathname}</output>
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <LocationProbe />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/books/:bookId" element={<p>书本详情</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('HomePage recommendations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getMe.mockResolvedValue({ nickname: '小明' })
    mocks.getProgress.mockResolvedValue([])
    mocks.getEpisodes.mockResolvedValue([])
    mocks.getMemories.mockResolvedValue([])
    mocks.getQuizSessions.mockResolvedValue([])
    mocks.getRecommendations.mockResolvedValue([])
  })

  afterEach(() => cleanup())

  it('加载时展示推荐 loading 状态', () => {
    mocks.getRecommendations.mockReturnValue(new Promise(() => undefined))
    renderPage()

    expect(screen.getByText('正在准备今日推荐…')).toBeTruthy()
  })

  it('成功返回推荐时展示标题、描述、理由并可进入相关书', async () => {
    mocks.getRecommendations.mockResolvedValue([recommendation])
    renderPage()

    expect(await screen.findByText(recommendation.title)).toBeTruthy()
    expect(screen.getByText(recommendation.description)).toBeTruthy()
    expect(screen.getByText(recommendation.reason)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: `打开推荐：${recommendation.title}` }))
    await waitFor(() => expect(screen.getByTestId('home-location').textContent).toBe('/books/book-1'))
  })

  it('没有推荐时展示轻量空态', async () => {
    renderPage()

    expect(await screen.findByText(/暂时没有新的推荐/)).toBeTruthy()
    expect(screen.getByText(/去书库找找想学的内容/)).toBeTruthy()
  })

  it('推荐 API 失败时展示降级提示且页面不崩溃', async () => {
    mocks.getRecommendations.mockRejectedValue(new Error('recommendations unavailable'))
    renderPage()

    expect(await screen.findByText(/推荐暂时不可用/)).toBeTruthy()
    expect(screen.getByRole('heading', { name: /晚上好/ })).toBeTruthy()
  })
})
