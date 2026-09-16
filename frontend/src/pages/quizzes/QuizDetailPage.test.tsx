// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getQuizSession: vi.fn(),
  getQuestions: vi.fn(),
  getAnswers: vi.fn(),
  getInteractions: vi.fn(),
  getQuizSessions: vi.fn(),
  getBook: vi.fn(),
  getChapter: vi.fn(),
  getChapters: vi.fn(),
  runIntent: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
  quizService: {
    getQuizSession: mocks.getQuizSession,
    getQuestions: mocks.getQuestions,
    getAnswers: mocks.getAnswers,
    getInteractions: mocks.getInteractions,
    getQuizSessions: mocks.getQuizSessions,
  },
  contentService: {
    getBook: mocks.getBook,
    getChapter: mocks.getChapter,
    getChapters: mocks.getChapters,
  },
}))

vi.mock('@/features/companion', () => ({
  useCompanionStore: { getState: () => ({ setOpen: vi.fn() }) },
  useTeacherName: () => '温暖老师',
}))

vi.mock('@/features/conversation', () => ({
  useConversationStore: (selector: (state: { runIntent: (i: string, s?: string, c?: unknown) => void }) => unknown) =>
    selector({ runIntent: mocks.runIntent }),
}))

import QuizDetailPage from './QuizDetailPage'
import type { QuizAnswer } from '@/entities/quiz/types'

afterEach(cleanup)

const sessionDetail = {
  quiz_session_id: 'quiz-9',
  student_id: 's-1',
  conversation_id: 'conv-1',
  teacher_role_id: null,
  book_id: 'book-2',
  chapter_id: 'chapter-4',
  title: '随堂测验',
  quiz_kind: 'CHAPTER_QUIZ',
  status: 'COMPLETED',
  result_summary: { correct: 1, total: 1, hints_used: 0 },
  ai_feedback: null,
  skill_version: 'quiz-v2',
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-01T08:00:00Z',
  completed_at: '2026-09-01T08:05:00Z',
  questions_snapshot: [
    {
      question_id: 'question-17',
      quiz_session_id: 'quiz-9',
      question_order: 1,
      question_type: 'MULTIPLE_CHOICE',
      stem: '以下哪些属于监督学习？',
      options: [
        { key: 'A', text: '老师给答案' },
        { key: 'C', text: '学生自己分组' },
      ],
      correct_answer: { keys: ['A', 'C'] },
      explanation: '监督学习用带答案的数据学映射；A、C 中 A 符合。',
      source_context: null,
      interaction_policy: { allow_hint: true, max_hint_level: 2 },
      knowledge_point_ids: [],
    },
  ],
}

function setup(answers: QuizAnswer[] = []) {
  mocks.getQuizSession.mockResolvedValue(sessionDetail)
  mocks.getQuestions.mockResolvedValue(sessionDetail.questions_snapshot ?? [])
  mocks.getAnswers.mockResolvedValue(answers)
  mocks.getInteractions.mockResolvedValue([])
  mocks.getBook.mockResolvedValue({ title: '人工智能初探' })
  mocks.getChapter.mockResolvedValue({ title: '监督学习' })
  mocks.getChapters.mockResolvedValue([])
  return render(
    <MemoryRouter initialEntries={['/quizzes/quiz-9']}>
      <Routes>
        <Route path="/quizzes/:quizId" element={<QuizDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('QuizDetailPage 答卷操作明确（T15）', () => {
  it('多选 A/C 显示两个选项文本（正确/作答均映射）', async () => {
    setup([{
      answer_id: 'a-1',
      quiz_session_id: 'quiz-9',
      question_id: 'question-17',
      student_id: 's-1',
      submitted_answer: { keys: ['A', 'C'] },
      is_correct: true,
      attempt_no: 1,
      hint_level_at_submit: 0,
      is_final: true,
      submitted_at: '2026-09-01T08:02:00Z',
      created_at: '2026-09-01T08:02:00Z',
    }])
    await waitFor(() => expect(screen.getByText('随堂测验')).toBeTruthy())
    // 你的答案：A；C（答案键与正确答案键可能同值，允许多个匹配）
    expect(screen.getAllByText('A, C').length).toBeGreaterThan(0)
    // 两个选项文本都展示（作答行与正确答案行各一次）
    expect(screen.getAllByText('老师给答案；学生自己分组').length).toBe(2)
    expect(screen.getByText('解析')).toBeTruthy()
  })

  it('讲解这道题传明确 questionId 且只读（0 次写接口）', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('随堂测验')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('讲解这道题')).toBeTruthy())
    fireEvent.click(screen.getByText('讲解这道题'))
    expect(mocks.runIntent).toHaveBeenCalledWith(
      'explain-question',
      undefined,
      expect.objectContaining({ quizSessionId: 'quiz-9', questionId: 'question-17' }),
    )
    // 只读：仅 get* 被调用，绝无创建/提交（0 次写接口）。
    expect(mocks.getQuizSession).toHaveBeenCalled()
    expect(mocks.getQuestions).toHaveBeenCalled()
    expect(mocks.getAnswers).toHaveBeenCalled()
    expect(mocks.getInteractions).toHaveBeenCalled()
  })

  it('再练一道触发 quiz-requestion 且传 quizSessionId', async () => {
    setup()
    await waitFor(() => expect(screen.getByText('随堂测验')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('再练一道类似的')).toBeTruthy())
    fireEvent.click(screen.getByText('再练一道类似的'))
    expect(mocks.runIntent).toHaveBeenCalledWith(
      'quiz-requestion',
      undefined,
      expect.objectContaining({ quizSessionId: 'quiz-9' }),
    )
  })
})
