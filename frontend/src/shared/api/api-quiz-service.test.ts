import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { QuizAnswer, QuizQuestion, QuizSession } from '@/entities/quiz/types'

import { ApiQuizService } from './api-quiz-service'

function jsonResponse(
  status: number,
  body: unknown,
  headers: HeadersInit = {},
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
  } as Response
}

const session: QuizSession = {
  quiz_session_id: 'quiz-1',
  student_id: 'student-1',
  conversation_id: 'conversation-1',
  teacher_role_id: 'role-1',
  book_id: 'book-1',
  chapter_id: 'chapter-1',
  title: '训练数据 · 随堂测验',
  quiz_kind: 'CHAPTER_QUIZ',
  status: 'ACTIVE',
  result_summary: { correct: 0, total: 1, hints_used: 0 },
  ai_feedback: null,
  skill_version: 'quiz-v1',
  created_at: '2026-08-19T08:00:00Z',
  updated_at: '2026-08-19T08:00:00Z',
  completed_at: null,
}

const question: QuizQuestion = {
  question_id: 'question-1',
  quiz_session_id: 'quiz-1',
  question_order: 1,
  question_type: 'SINGLE_CHOICE',
  stem: '训练数据最重要的作用是什么？',
  options: [{ key: 'B', text: '发现规律' }],
  correct_answer: { key: 'B' },
  explanation: '帮助机器发现规律。',
  source_context: null,
  interaction_policy: { allow_hint: true, max_hint_level: 3 },
  knowledge_point_ids: ['training_data'],
}

const answer: QuizAnswer = {
  answer_id: 'answer-1',
  quiz_session_id: 'quiz-1',
  question_id: 'question-1',
  student_id: 'student-1',
  submitted_answer: { key: 'B' },
  is_correct: true,
  attempt_no: 1,
  hint_level_at_submit: 0,
  is_final: true,
  submitted_at: '2026-08-19T08:01:00Z',
  created_at: '2026-08-19T08:01:00Z',
}

describe('ApiQuizService', () => {
  let service: ApiQuizService

  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => 'token-1' } })
    vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiQuizService()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('创建测验时透传会话、内容、题数、难度和 quiz_kind', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(201, { data: session, meta: {} }),
    )

    await expect(
      service.createQuizSession({
        conversation_id: 'conversation-1',
        book_id: 'book-1',
        chapter_id: 'chapter-1',
        quiz_kind: 'CHAPTER_QUIZ',
        question_count: 3,
        difficulty: 'HARD',
      }),
    ).resolves.toEqual(session)

    expect(fetchMock.mock.calls[0]).toEqual([
      '/api/v1/quiz-sessions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          conversation_id: 'conversation-1',
          book_id: 'book-1',
          chapter_id: 'chapter-1',
          quiz_kind: 'CHAPTER_QUIZ',
          question_count: 3,
          difficulty: 'HARD',
        }),
      }),
    ])
  })

  it('读取历史、详情、题目、答卷和互动审计', async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, { data: [session], meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: session, meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: [question], meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: [answer], meta: {} }))
      .mockResolvedValueOnce(jsonResponse(200, { data: [], meta: {} }))

    await expect(
      service.getQuizSessions({
        limit: 20,
        quiz_kind: 'CHAPTER_QUIZ',
        status: 'ACTIVE',
      }),
    ).resolves.toEqual([session])
    await expect(service.getQuizSession('quiz-1')).resolves.toEqual(session)
    await expect(service.getQuestions('quiz-1')).resolves.toEqual([question])
    await expect(service.getAnswers('quiz-1')).resolves.toEqual([answer])
    await expect(service.getInteractions('quiz-1')).resolves.toEqual([])

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/quiz-sessions?limit=20&quiz_kind=CHAPTER_QUIZ&status=ACTIVE',
      '/api/v1/quiz-sessions/quiz-1',
      '/api/v1/quiz-sessions/quiz-1/questions',
      '/api/v1/quiz-sessions/quiz-1/answers',
      '/api/v1/quiz-sessions/quiz-1/interactions',
    ])
  })

  it('提交答案自动附加 Idempotency-Key，并接受重放响应', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: answer, meta: {} }, { 'Idempotency-Replayed': 'true' }),
    )

    await expect(
      service.submitAnswer('quiz-1', 'question-1', {
        answer: { key: 'B' },
        hint_level_at_submit: 1,
      }),
    ).resolves.toEqual(answer)

    expect(fetchMock.mock.calls[0]).toEqual([
      '/api/v1/quiz-sessions/quiz-1/questions/question-1/answers',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ answer: { key: 'B' }, hint_level_at_submit: 1 }),
        headers: expect.objectContaining({
          Authorization: 'Bearer token-1',
          'Idempotency-Key': 'request-1',
        }),
      }),
    ])
  })

  it('请求提示走 POST hints，并将 401 转为 ApiError', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(201, {
        data: {
          hint_level: 1,
          hint_text: '先想想规律。',
          max_hint_level: 3,
          interaction_id: 'interaction-1',
        },
        meta: {},
      }),
    )

    await expect(service.requestHint('quiz-1', 'question-1')).resolves.toMatchObject({
      hint_level: 1,
      hint_text: '先想想规律。',
    })
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/quiz-sessions/quiz-1/questions/question-1/hints',
    )

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, {
        error: { code: 'UNAUTHENTICATED', message: 'missing bearer token' },
      }),
    )
    await expect(service.getQuizSessions()).rejects.toEqual(
      expect.objectContaining({ status: 401, code: 'UNAUTHENTICATED' }),
    )
  })
})
