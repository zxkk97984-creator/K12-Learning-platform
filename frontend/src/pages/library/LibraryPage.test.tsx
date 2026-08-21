// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BookProgress } from '@/entities/book/types'
import { mockBooks } from '@/mocks/data/books'

vi.mock('@/mocks/services', () => ({
  contentService: {
    getBooks: vi.fn(),
    getProgress: vi.fn(),
  },
}))

import { contentService } from '@/mocks/services'
import LibraryPage from './LibraryPage'

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
    <MemoryRouter initialEntries={['/library']}>
      <LocationProbe />
      <Routes>
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/books/:bookId" element={<p>书本详情页</p>} />
        <Route path="/learn/:bookId/:chapterId" element={<p>学习页</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LibraryPage book detail entry points', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(contentService.getBooks).mockResolvedValue(books)
    vi.mocked(contentService.getProgress).mockResolvedValue([])
  })

  afterEach(() => cleanup())

  it('在为你精选和全部书籍两处书卡都提供详情入口', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '为你精选' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '全部书籍' })).toBeTruthy()

    const articles = screen.getAllByRole('article')
    expect(articles).toHaveLength(books.length * 2)
    for (const article of articles) {
      expect(within(article).getByRole('button', { name: '详情' })).toBeTruthy()
    }
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
})
