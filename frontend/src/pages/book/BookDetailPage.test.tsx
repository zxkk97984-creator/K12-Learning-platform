// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Book, BookProgress, Chapter, ChapterDetail } from '@/entities/book/types'

vi.mock('@/shared/services', () => ({
  contentService: {
    getBooks: vi.fn(),
    getBook: vi.fn(),
    getChapters: vi.fn(),
    getChapter: vi.fn(),
    getKnowledgePoint: vi.fn(),
    getProgress: vi.fn(),
    getBookProgress: vi.fn(),
  },
}))

import { contentService } from '@/shared/services'
import BookDetailPage from './BookDetailPage'

const book: Book = {
  book_id: 'book-1',
  title: 'AI 不是魔法',
  cover_url: null,
  description: '从推荐系统、训练数据到算法公平，建立一张看懂 AI 的地图。',
  grade_min: 7,
  grade_max: 9,
  difficulty: 'MEDIUM',
  estimated_minutes: 90,
  author: null,
  tags: ['AI 基础', '训练数据'],
  keywords: '训练数据 · 标签 · 算法',
  book_no: '01',
  tint: 1,
  status: 'PUBLISHED',
  chapter_count: 2,
  source_ids: [],
  license: null,
  copyright_status: null,
}

const chapters: Chapter[] = [
  {
    chapter_id: 'chapter-1',
    book_id: 'book-1',
    title: '从“会回答”开始',
    chapter_order: 1,
    summary: '先认识 AI 的基本能力。',
    estimated_minutes: 20,
    status: 'PUBLISHED',
    is_completed: true,
  },
  {
    chapter_id: 'chapter-2',
    book_id: 'book-1',
    title: '推荐系统看见了什么',
    chapter_order: 2,
    summary: '看看推荐系统如何使用数据。',
    estimated_minutes: 25,
    status: 'PUBLISHED',
    is_completed: false,
  },
]

const chapterDetail: ChapterDetail = {
  ...chapters[0],
  content_blocks: [],
  knowledge_points: [
    {
      knowledge_point_id: 'kp-1',
      name: '训练数据',
      slug: 'training-data',
      description: '帮助机器发现规律的例子。',
      topic: 'AI 基础',
      parent_id: null,
      status: 'ACTIVE',
    },
  ],
}

const progress: BookProgress = {
  progress_id: 'progress-1',
  student_id: 'student-1',
  book_id: 'book-1',
  chapter_id: 'chapter-2',
  block_id: null,
  status: 'READING',
  position_percent: 62,
  last_read_at: '2026-08-20T08:00:00Z',
  started_at: '2026-08-19T08:00:00Z',
  completed_at: null,
  total_seconds: 1200,
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-path">{location.pathname}</output>
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/books/book-1']}>
      <LocationProbe />
      <Routes>
        <Route path="/books/:bookId" element={<BookDetailPage />} />
        <Route path="/learn/:bookId/:chapterId" element={<p>学习页</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('BookDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(contentService.getBook).mockResolvedValue(book)
    vi.mocked(contentService.getChapters).mockResolvedValue(chapters)
    vi.mocked(contentService.getChapter).mockResolvedValue(chapterDetail)
    vi.mocked(contentService.getBookProgress).mockResolvedValue(null)
  })

  afterEach(() => cleanup())

  it('渲染书名、简介、适用年级和预计学习时间', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: 'AI 不是魔法' })).toBeTruthy()
    expect(screen.getByText(book.description ?? '')).toBeTruthy()
    expect(screen.getByText(/初中/)).toBeTruthy()
    expect(screen.getByText(/90 分钟/)).toBeTruthy()
  })

  it('有进度时显示继续学习并进入当前章节', async () => {
    vi.mocked(contentService.getBookProgress).mockResolvedValue(progress)
    renderPage()

    const button = await screen.findByRole('button', { name: '继续学习' })
    expect(screen.getByText(/62%/)).toBeTruthy()
    fireEvent.click(button)

    await waitFor(() =>
      expect(screen.getByTestId('location-path').textContent).toBe('/learn/book-1/chapter-2'),
    )
  })

  it('无进度时显示开始学习并进入第一章', async () => {
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '开始学习' }))

    await waitFor(() =>
      expect(screen.getByTestId('location-path').textContent).toBe('/learn/book-1/chapter-1'),
    )
  })

  it('渲染章节序号、标题、时长和完成状态', async () => {
    renderPage()

    expect(await screen.findByText('从“会回答”开始')).toBeTruthy()
    expect(screen.getByText('第 1 章')).toBeTruthy()
    expect(screen.getByText('推荐系统看见了什么')).toBeTruthy()
    expect(screen.getByText('第 2 章')).toBeTruthy()
    expect(screen.getByText('已完成')).toBeTruthy()
  })

  it('章节获取失败时展示暂无内容并禁用开始学习', async () => {
    vi.mocked(contentService.getChapters).mockRejectedValueOnce(new Error('chapters unavailable'))
    renderPage()

    expect(await screen.findByText('暂无内容')).toBeTruthy()
    expect(screen.getByText('章节暂时无法加载，请稍后再试。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '暂无内容' })).toHaveProperty('disabled', true)
  })

  it('章节详情有知识点时展示你将学会什么', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '你将学会什么' })).toBeTruthy()
    expect(screen.getByText('训练数据')).toBeTruthy()
    expect(screen.getByText('帮助机器发现规律的例子。')).toBeTruthy()
  })

  it('章节详情没有知识点时隐藏你将学会什么', async () => {
    vi.mocked(contentService.getChapter).mockResolvedValueOnce({
      ...chapterDetail,
      knowledge_points: [],
    })
    renderPage()

    await screen.findByRole('heading', { name: 'AI 不是魔法' })
    await waitFor(() => expect(screen.queryByRole('heading', { name: '你将学会什么' })).toBeNull())
  })
})
