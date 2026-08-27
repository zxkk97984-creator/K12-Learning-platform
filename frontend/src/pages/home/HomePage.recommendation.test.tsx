// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Recommendation } from '@/shared/api/recommendation-service'

const mocks = vi.hoisted(() => ({
  dismissRecommendation: vi.fn(),
  getMe: vi.fn(),
  getProgress: vi.fn(),
  getBook: vi.fn(),
  getChapter: vi.fn(),
  getEpisodes: vi.fn(),
  getMemories: vi.fn(),
  getQuizSessions: vi.fn(),
  getRecommendations: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
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
  recommendationService: {
    getRecommendations: mocks.getRecommendations,
    dismissRecommendation: mocks.dismissRecommendation,
  },
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    currentUser: { nickname: '小明', grade: 8, learning_goal: '期末冲刺' },
    authUser: { user_type: 'STUDENT' },
  }),
}))

vi.mock('@/features/companion', () => ({
  CompanionSprite: () => <span aria-hidden="true" />,
  useCompanionStore: { getState: () => ({ setOpen: vi.fn() }) },
  // Phase 4 验收：使用非硬编码的 mock 教师名
  useTeacherName: () => '温暖老师',
}))

vi.mock('@/features/conversation', () => ({
  useConversationStore: (selector: (state: { runIntent: () => void }) => unknown) =>
    selector({ runIntent: vi.fn() }),
}))

import HomePage from './HomePage'
import { ScreenContextProvider } from '@/features/screen-context'

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
    <ScreenContextProvider>
      <MemoryRouter initialEntries={['/']}>
        <LocationProbe />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/books/:bookId" element={<p>书本详情</p>} />
        </Routes>
      </MemoryRouter>
    </ScreenContextProvider>,
  )
}

describe('HomePage recommendations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getMe.mockResolvedValue({
      nickname: '小明',
      learning_days: 3,
      total_learning_minutes: 42,
      completed_books: 1,
      completed_chapters: 4,
      quiz_count: 5,
    })
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

  it('点击「不感兴趣」调用 dismiss 并从列表移除对应卡片', async () => {
    const dismissed = { ...recommendation, status: 'DISMISSED' as const }
    // 首次返回推荐；dismiss 后的刷新返回空
    mocks.getRecommendations
      .mockResolvedValueOnce([recommendation])
      .mockResolvedValue([dismissed])
    mocks.dismissRecommendation.mockResolvedValue(dismissed)

    renderPage()
    expect(await screen.findByText(recommendation.title)).toBeTruthy()

    fireEvent.click(screen.getByTestId('home-dismiss-recommendation-1'))

    await waitFor(() =>
      expect(mocks.dismissRecommendation).toHaveBeenCalledWith('recommendation-1'),
    )
    await waitFor(() => {
      expect(screen.queryByText(recommendation.title)).toBeNull()
    })
  })

  it('有进度时展示完整继续学习卡（书名/章节/百分比/最近阅读/按钮），并使用 mock 教师名', async () => {
    mocks.getProgress.mockResolvedValue([
      {
        progress_id: 'p-9',
        student_id: 'student-1',
        book_id: 'book-1',
        chapter_id: 'ch-2',
        block_id: null,
        status: 'READING',
        position_percent: 55,
        last_read_at: '2026-08-24T19:30:00Z',
        total_seconds: 600,
        started_at: '2026-08-20T08:00:00Z',
        completed_at: null,
        created_at: '2026-08-20T08:00:00Z',
        updated_at: '2026-08-24T19:30:00Z',
      },
    ])
    mocks.getBook.mockResolvedValue({ book_id: 'book-1', title: 'AI 不是魔法', description: '面向初学者的 AI 入门' })
    mocks.getChapter.mockResolvedValue({
      chapter_id: 'ch-2',
      book_id: 'book-1',
      title: '训练数据',
      chapter_order: 2,
      summary: '本章讲训练数据与标签的关系。',
      estimated_minutes: 13,
      content_blocks: [],
      knowledge_points: [],
    })

    renderPage()

    // 加载完成后不出现 loading，也不出现空态
    expect(await screen.findByTestId('continue-learning')).toBeTruthy()
    expect(screen.queryByTestId('continue-loading')).toBeNull()
    expect(screen.queryByTestId('continue-empty')).toBeNull()

    expect(screen.getByText(/第 2 章 · 训练数据/)).toBeTruthy()
    expect(screen.getByText(/55%/)).toBeTruthy()
    expect(screen.getByText(/最近阅读/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '继续第 2 章 →' })).toBeTruthy()
    // 动态教师名来自 useTeacherName mock
    expect(screen.getAllByText(/温暖老师/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/霜铃/)).toBeNull()
  })

  it('无进度时显示明确空态而非加载态', async () => {
    renderPage()
    expect(await screen.findByTestId('continue-empty')).toBeTruthy()
    expect(screen.getByText(/还没有开始学习/)).toBeTruthy()
    expect(screen.queryByTestId('continue-loading')).toBeNull()
    expect(screen.queryByTestId('continue-learning')).toBeNull()
  })

  it('空 memories/episodes/quizzes 时显示明确空态且不出现伪造文案', async () => {
    renderPage()
    expect(await screen.findByTestId('memories-empty')).toBeTruthy()
    expect(screen.getByTestId('episodes-empty')).toBeTruthy()
    expect(screen.getByTestId('quizzes-empty')).toBeTruthy()
    // 不再回退到硬编码画像文案 / 标签
    expect(screen.queryByText(/你喜欢通过例子学习/)).toBeNull()
    expect(screen.queryByText('例子优先')).toBeNull()
    // 真实统计条渲染（来自 getMe 数据库列）
    expect(screen.getByTestId('learning-stats').textContent).toContain('学习天数 · 3')
    expect(screen.getByTestId('learning-stats').textContent).toContain('测验次数 · 5')
  })
})
