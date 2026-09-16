// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BookProgress } from '@/entities/book/types'
import { mockBooks } from '@/mocks/data/books'

const mocks = vi.hoisted(() => ({
  recommendationService: {
    getRecommendations: vi.fn(),
    dismissRecommendation: vi.fn(),
  },
}))

vi.mock('@/shared/services', () => ({
  contentService: {
    getBooksPage: vi.fn(),
    getProgress: vi.fn(),
  },
  recommendationService: mocks.recommendationService,
}))

import { contentService } from '@/shared/services'
import LibraryPage from './LibraryPage'
import { ScreenContextProvider } from '@/features/screen-context'

const books = mockBooks.slice(0, 2)

const progress: BookProgress = {
  progress_id: 'progress-1',
  student_id: 'student-1',
  book_id: 'b1',
  chapter_id: 'ch3',
  block_id: null,
  status: 'READING',
  position_percent: 42,
  last_read_at: '2026-08-20T08:00:00Z',
  started_at: '2026-08-19T08:00:00Z',
  completed_at: null,
  total_seconds: 900,
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-path">{location.pathname}</output>
}

function renderPage() {
  return render(
    <ScreenContextProvider>
      <MemoryRouter initialEntries={['/library']}>
        <LocationProbe />
        <Routes>
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/books/:bookId" element={<p>书本详情页</p>} />
          <Route path="/learn/:bookId/:chapterId" element={<p>学习页</p>} />
        </Routes>
      </MemoryRouter>
    </ScreenContextProvider>,
  )
}

describe('LibraryPage book detail entry points', () => {
  beforeEach(() => {
    mocks.recommendationService.getRecommendations.mockResolvedValue([])
  })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(contentService.getBooksPage).mockResolvedValue({
      items: books,
      meta: { next_cursor: null, has_more: false, total: books.length },
    })
    vi.mocked(contentService.getProgress).mockResolvedValue([])
  })

  afterEach(() => cleanup())

  it('精选区来自真实推荐 API：展示理由、可忽略，详情入口可用', async () => {
    // Phase 3：精选不再取静态前 3 本，而是消费推荐接口并渲染真实 reason
    // 首次返回推荐；dismiss 后的刷新返回空（模拟已移除）
    mocks.recommendationService.getRecommendations
      .mockResolvedValueOnce([
      {
        recommendation_id: 'rec-1',
        recommendation_type: 'CONTINUE_READING',
        title: '继续阅读《b1》',
        description: '从上次位置继续最顺畅。',
        reason: '你已完成《b1》的 42%，保持节奏能减少重新熟悉内容的成本。',
        evidence_ids: ['progress-1'],
        related_book_id: 'b1',
        status: 'ACTIVE',
        created_at: '2026-08-24T00:00:00Z',
        updated_at: '2026-08-24T00:00:00Z',
      },
      ])
      .mockResolvedValue([])
    renderPage()

    expect(await screen.findByRole('heading', { name: '为你精选' })).toBeTruthy()
    // 精选区：推荐映射到的书籍卡片 + 真实理由文案
    const reason = await screen.findByText(/保持节奏能减少重新熟悉内容的成本/)
    expect(reason).toBeTruthy()
    expect(screen.getByTestId('dismiss-rec-1')).toBeTruthy()

    // 全部书籍区仍然提供详情入口
    const detailButtons = await screen.findAllByRole('button', { name: '详情' })
    expect(detailButtons.length).toBeGreaterThanOrEqual(books.length)

    // dismiss：调用真实服务并从精选中移除
    mocks.recommendationService.dismissRecommendation.mockResolvedValue({
      recommendation_id: 'rec-1',
      recommendation_type: 'CONTINUE_READING',
      title: '',
      description: '',
      reason: '',
      evidence_ids: [],
      related_book_id: 'b1',
      status: 'DISMISSED',
      created_at: '2026-08-24T00:00:00Z',
      updated_at: '2026-08-24T00:00:00Z',
    } as never)
    fireEvent.click(screen.getByTestId('dismiss-rec-1'))
    await waitFor(() =>
      expect(mocks.recommendationService.dismissRecommendation).toHaveBeenCalledWith('rec-1'),
    )
    await waitFor(() => {
      const remaining = screen.queryByText(/保持节奏能减少重新熟悉内容的成本/)
      expect(remaining).toBeNull()
    })
  })

  it('全部书籍网格为每本书提供详情入口', async () => {
    renderPage()
    await screen.findByRole('heading', { name: '全部书籍' })
    const detailButtons = await screen.findAllByRole('button', { name: '详情' })
    expect(detailButtons.length).toBe(books.length)
  })

  it('无进度时点击书名或详情都进入书本详情页', async () => {
    renderPage()

    const titleButtons = await screen.findAllByRole('button', { name: books[0].title })
    fireEvent.click(titleButtons[0])
    await waitFor(() =>
      expect(screen.getByTestId('location-path').textContent).toBe('/books/b1'),
    )

    cleanup()
    renderPage()
    const detailButtons = await screen.findAllByRole('button', { name: '详情' })
    fireEvent.click(detailButtons[0])
    await waitFor(() =>
      expect(screen.getByTestId('location-path').textContent).toBe('/books/b1'),
    )
  })

  it('保留继续学习入口并继续进入当前章节', async () => {
    vi.mocked(contentService.getProgress).mockResolvedValue([progress])
    renderPage()

    fireEvent.click((await screen.findAllByRole('button', { name: '继续 →' }))[0])
    await waitFor(() =>
      expect(screen.getByTestId('location-path').textContent).toBe('/learn/b1/ch3'),
    )
  })

  it('全部书籍列表不再渲染静态推荐入口（Phase 3 缺口 2）', async () => {
    mocks.recommendationService.getRecommendations.mockResolvedValue([])
    renderPage()

    await screen.findByRole('heading', { name: '全部书籍' })
    // 无推荐时，任何位置都不应出现静态「为什么推荐？」按钮
    expect(screen.queryAllByText('为什么推荐？')).toHaveLength(0)
  })
})

describe('LibraryPage 分页、错误与后端搜索', () => {
  beforeEach(() => {
    mocks.recommendationService.getRecommendations.mockResolvedValue([])
    vi.clearAllMocks()
    vi.mocked(contentService.getProgress).mockResolvedValue([])
  })

  afterEach(() => cleanup())

  it('负载更多：追加下一页并保留前页，游标由 meta 提供', async () => {
    vi.mocked(contentService.getBooksPage)
      .mockResolvedValueOnce({
        items: [books[0]],
        meta: { next_cursor: 'cursor-2', has_more: true, total: 2 },
      })
      .mockResolvedValueOnce({
        items: [books[1]],
        meta: { next_cursor: null, has_more: false, total: 2 },
      })

    renderPage()
    expect(await screen.findByRole('button', { name: books[0].title })).toBeTruthy()
    const loadMore = await screen.findByRole('button', { name: /加载更多/ })
    fireEvent.click(loadMore)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: books[1].title })).toBeTruthy(),
    )
    expect(contentService.getBooksPage).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: 'cursor-2' }),
    )
  })

  it('加载失败显示错误与重试，不声称没有书', async () => {
    vi.mocked(contentService.getBooksPage).mockRejectedValueOnce(new Error('network down'))
    renderPage()
    expect(await screen.findByRole('heading', { name: '暂时无法加载书库' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
  })

  it('搜索输入防抖后调用后端（非本地过滤）', async () => {
    vi.mocked(contentService.getBooksPage).mockResolvedValue({
      items: [books[0]],
      meta: { next_cursor: null, has_more: false, total: 1 },
    })
    renderPage()
    await screen.findByRole('button', { name: books[0].title })

    fireEvent.change(screen.getByLabelText('搜索书库'), { target: { value: '训练' } })
    await waitFor(() =>
      expect(contentService.getBooksPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: '训练' }),
      ),
    )
  })
})
