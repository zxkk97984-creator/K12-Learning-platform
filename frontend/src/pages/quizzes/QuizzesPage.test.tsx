// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { QuizSession } from '@/entities/quiz/types'

const mocks = vi.hoisted(() => ({
  getQuizSessions: vi.fn(),
  getBook: vi.fn(),
  getChapter: vi.fn(),
  getChapters: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
  quizService: { getQuizSessions: mocks.getQuizSessions },
  contentService: {
    getBook: mocks.getBook,
    getChapter: mocks.getChapter,
    getChapters: mocks.getChapters,
  },
}))

vi.mock('@/features/companion', () => ({ useTeacherName: () => '温暖老师' }))

import QuizzesPage from './QuizzesPage'

afterEach(cleanup)

const sessions: QuizSession[] = [
  {
    quiz_session_id: 'quiz-1',
    student_id: 's-1',
    conversation_id: 'conv-1',
    teacher_role_id: null,
    book_id: 'book-1',
    chapter_id: 'chapter-1',
    title: '随堂测验一',
    quiz_kind: 'CHAPTER_QUIZ',
    status: 'COMPLETED',
    result_summary: { correct: 3, total: 5, hints_used: 0 },
    ai_feedback: null,
    skill_version: 'quiz-v2',
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-01T08:00:00Z',
    completed_at: '2026-09-01T08:06:00Z',
  },
]

function setup() {
  return render(
    <MemoryRouter initialEntries={['/quizzes']}>
      <Routes>
        <Route path="/quizzes" element={<QuizzesPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('QuizzesPage 历史筛选与恢复（T15）', () => {
  it('来源查询失败不抹掉整份列表（单来源失败可容错）', async () => {
    mocks.getQuizSessions.mockResolvedValue(sessions)
    // quizSource 内部 getBook 抛错 → 应降级为占位，而非丢掉整份列表。
    mocks.getBook.mockRejectedValue(new Error('boom'))
    mocks.getChapters.mockRejectedValue(new Error('boom'))
    setup()
    await waitFor(() => expect(screen.getByText('随堂测验一')).toBeTruthy())
    // 列表仍展示，来源降级为占位（book/chapter 各显示 —）。
    expect(screen.getByText(/《—》/)).toBeTruthy()
  })

  it('加载失败显示错误并可重试', async () => {
    mocks.getQuizSessions.mockRejectedValueOnce(new Error('network'))
    mocks.getQuizSessions.mockResolvedValueOnce(sessions)
    mocks.getBook.mockResolvedValue({ title: '人工智能初探' })
    mocks.getChapter.mockResolvedValue({ title: '监督学习' })
    mocks.getChapters.mockResolvedValue([])
    setup()
    await waitFor(() => expect(screen.getByText('加载测验记录失败')).toBeTruthy())
    fireEvent.click(screen.getByText('重新加载'))
    await waitFor(() => expect(screen.getByText('随堂测验一')).toBeTruthy())
  })
})
