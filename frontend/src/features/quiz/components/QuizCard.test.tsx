// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { QuizAnswer, QuizQuestion, QuizSession } from '@/entities/quiz/types'

import { QuizCard } from './QuizCard'

function jsonResponse(status: number, body: unknown, headers: HeadersInit = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
  } as Response
}

const questions: QuizQuestion[] = [
  {
    question_id: 'question-1',
    quiz_session_id: 'quiz-1',
    question_order: 1,
    question_type: 'SINGLE_CHOICE',
    stem: '本章的核心知识点是哪一个？',
    options: [
      { key: 'A', text: '选项甲' },
      { key: 'B', text: '选项乙' },
      { key: 'C', text: '选项丙' },
      { key: 'D', text: '选项丁' },
    ],
    correct_answer: { key: 'B' },
    explanation: '解析一：来自服务端。',
    source_context: null,
    interaction_policy: { allow_hint: true, max_hint_level: 3 },
    knowledge_point_ids: [],
  },
  {
    question_id: 'question-2',
    quiz_session_id: 'quiz-1',
    question_order: 2,
    question_type: 'MULTIPLE_CHOICE',
    stem: '本章涉及哪些内容？（多选）',
    options: [
      { key: 'A', text: '知识点一' },
      { key: 'B', text: '知识点二' },
      { key: 'C', text: '干扰项' },
      { key: 'D', text: '知识点三' },
    ],
    correct_answer: { keys: ['A', 'B'] },
    explanation: '解析二：来自服务端。',
    source_context: null,
    interaction_policy: { allow_hint: true, max_hint_level: 3 },
    knowledge_point_ids: [],
  },
  {
    question_id: 'question-3',
    quiz_session_id: 'quiz-1',
    question_order: 3,
    question_type: 'FILL_BLANK',
    stem: '根据本章内容填空：机器从例子中发现的是____。',
    options: [],
    correct_answer: { value: '规律' },
    explanation: '解析三：来自服务端。',
    source_context: null,
    interaction_policy: { allow_hint: true, max_hint_level: 3 },
    knowledge_point_ids: [],
  },
]

function makeSession(overrides: Partial<QuizSession> = {}): QuizSession {
  return {
    quiz_session_id: 'quiz-1',
    student_id: 'student-1',
    conversation_id: null,
    teacher_role_id: null,
    book_id: null,
    chapter_id: null,
    title: '测试章节 · 随堂测验',
    quiz_kind: 'CHAPTER_QUIZ',
    status: 'ACTIVE',
    result_summary: { correct: 0, total: 3, hints_used: 0 },
    ai_feedback: null,
    skill_version: 'quiz-v2',
    created_at: '2026-08-19T08:00:00Z',
    updated_at: '2026-08-19T08:00:00Z',
    completed_at: null,
    ...overrides,
  }
}

describe('QuizCard multi-question real API interaction', () => {
  let submittedAnswers: Array<{ questionId: string; payload: Record<string, unknown>; headers: Headers }>
  let idempotencyHeader: string | null
  let authHeader: string | null

  beforeEach(() => {
    submittedAnswers = []
    idempotencyHeader = null
    authHeader = null
    window.localStorage.setItem('shuangling-access-token', 'token-1')
    vi.stubGlobal('crypto', { randomUUID: () => 'idem-fixed' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method ?? 'GET').toUpperCase()
        if (url.endsWith('/questions')) {
          const revealed = new Set(submittedAnswers.map((item) => item.questionId))
          return jsonResponse(200, {
            data: questions.map((item) => ({
              ...item,
              correct_answer:
                revealed.has(item.question_id) || submittedAnswers.length >= 3
                  ? item.correct_answer
                  : item.correct_answer,
            })),
            meta: {},
          })
        }
        if (/\/quiz-sessions\/quiz-1$/.test(url)) {
          const allFinal =
            submittedAnswers.filter((item) => item.payload !== null).length >= 3 &&
            new Set(submittedAnswers.map((i) => i.questionId)).size === 3
          const correctCount = submittedAnswers.filter((item) =>
            JSON.stringify(item.payload).includes('"B"') ||
            JSON.stringify(item.payload).includes('["A","B"]') ||
            JSON.stringify(item.payload).includes('规律'),
          ).length
          return jsonResponse(200, {
            data: makeSession(
              allFinal
                ? {
                    status: 'COMPLETED',
                    result_summary: { correct: Math.min(correctCount, 3), total: 3, hints_used: 0 },
                    ai_feedback: '本次完成得不错。',
                    completed_at: '2026-08-19T08:05:00Z',
                  }
                : {},
            ),
            meta: {},
          })
        }
        if (url.endsWith('/answers')) {
          if (method === 'GET') {
            const rows: QuizAnswer[] = submittedAnswers.map((item, index) => ({
              answer_id: `answer-${index}`,
              quiz_session_id: 'quiz-1',
              question_id: item.questionId,
              student_id: 'student-1',
              submitted_answer: item.payload,
              is_correct: item.questionId === 'question-3' || item.payload !== null,
              attempt_no: 1,
              hint_level_at_submit: 0,
              is_final: true,
              submitted_at: '2026-08-19T08:01:00Z',
              created_at: '2026-08-19T08:01:00Z',
            }))
            return jsonResponse(200, { data: rows, meta: {} })
          }
          // POST 提交答案
          idempotencyHeader = new Headers(init?.headers).get('idempotency-key')
          authHeader = new Headers(init?.headers).get('authorization')
          const body = JSON.parse(String(init?.body ?? '{}')) as {
            question_path?: string
            answer?: Record<string, unknown>
          }
          const questionId = url.match(/questions\/([^/]+)\/answers/)?.[1] ?? 'question-1'
          submittedAnswers.push({
            questionId,
            payload: (body.answer as Record<string, unknown>) ?? {},
            headers: new Headers(),
          })
          return jsonResponse(201, {
            data: {
              answer_id: `answer-${submittedAnswers.length}`,
              quiz_session_id: 'quiz-1',
              question_id: questionId,
              student_id: 'student-1',
              submitted_answer: body.answer ?? {},
              is_correct: true,
              attempt_no: 1,
              hint_level_at_submit: 0,
              is_final: true,
              submitted_at: '2026-08-19T08:01:00Z',
              created_at: '2026-08-19T08:01:00Z',
            },
            meta: {},
          })
        }
        throw new Error(`unexpected fetch: ${url}`)
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    cleanup()
  })

  it('多题推进：单选→多选→填空全部完成后展示真实 result_summary', async () => {
    render(<QuizCard sessionId="quiz-1" />)

    // 第 1 题：单选
    expect(await screen.findByText(/第 1 题 \/ 共 3 题/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /选项乙/ }))
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }))
    await waitFor(() => expect(screen.getByText(/✓ 答对了/)).toBeTruthy())
    await waitFor(() => expect(screen.getByText(/解析一：来自服务端。/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: '下一题 →' }))

    // 第 2 题：多选
    expect(await screen.findByText(/第 2 题 \/ 共 3 题/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /知识点一/ }))
    fireEvent.click(screen.getByRole('button', { name: /知识点二/ }))
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }))
    await waitFor(() => expect(screen.getAllByText(/✓ 答对了/).length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: '下一题 →' }))

    // 第 3 题：填空
    expect(await screen.findByText(/第 3 题 \/ 共 3 题/)).toBeTruthy()
    fireEvent.input(screen.getByLabelText('填空答案'), { target: { value: '规律' } })
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }))
    fireEvent.click(await screen.findByRole('button', { name: '查看结果' }))

    // 完成态：真实汇总，不出现硬编码「训练数据」文案
    expect(await screen.findByText(/测验完成 · 最终正确 3\/3/)).toBeTruthy()
    expect(screen.getByText(/本次完成得不错。/)).toBeTruthy()
    expect(screen.queryByText(/训练数据/)).toBeNull()

    // 三次提交均带 Idempotency-Key 与鉴权头
    expect(idempotencyHeader).toBe('idem-fixed')
    expect(authHeader).toBe('Bearer token-1')

    // 校验各题型 payload 形状
    const byQuestion = new Map(submittedAnswers.map((item) => [item.questionId, item.payload]))
    expect(byQuestion.get('question-1')).toEqual({ key: 'B' })
    expect(byQuestion.get('question-2')).toEqual({ keys: ['A', 'B'] })
    expect(byQuestion.get('question-3')).toEqual({ value: '规律' })
  })

  it('刷新后能从未完成的题目恢复（第 1 题已有最终作答）', async () => {
    submittedAnswers.push({
      questionId: 'question-1',
      payload: { key: 'B' },
      headers: new Headers(),
    })
    render(<QuizCard sessionId="quiz-1" />)
    expect(await screen.findByText(/第 2 题 \/ 共 3 题/)).toBeTruthy()
  })

  it('题目加载失败时展示降级文案', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(500, { error: { code: 'INTERNAL', message: 'boom' } }),
    )
    render(<QuizCard sessionId="quiz-1" />)
    await waitFor(() => expect(screen.getByText('题目加载失败')).toBeTruthy())
  })
})
