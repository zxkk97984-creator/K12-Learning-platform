// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { QuizAnswer, QuizQuestion } from '@/entities/quiz/types'

import { QuizCard } from './QuizCard'

function jsonResponse(status: number, body: unknown, headers: HeadersInit = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
  } as Response
}

const question: QuizQuestion = {
  question_id: 'question-1',
  quiz_session_id: 'quiz-1',
  question_order: 1,
  question_type: 'SINGLE_CHOICE',
  stem: '训练数据最重要的作用是什么？',
  options: [{ key: 'B', text: '让机器从例子中发现可重复的规律' }],
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

describe('QuizCard real API interaction', () => {
  let answerRequestHeaders: Headers | null = null

  beforeEach(() => {
    answerRequestHeaders = null
    window.localStorage.setItem('shuangling-access-token', 'token-1')
    vi.stubGlobal('crypto', { randomUUID: () => 'idem-1' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/questions')) {
          return jsonResponse(200, { data: [question], meta: {} })
        }
        if (url.endsWith('/answers')) {
          answerRequestHeaders = new Headers(init?.headers)
          return jsonResponse(201, { data: answer, meta: {} })
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

  it('加载真实题目并提交答案，附带 Idempotency-Key', async () => {
    render(<QuizCard sessionId="quiz-1" />)

    const option = await screen.findByRole('button', { name: /让机器从例子中发现可重复的规律/ })
    fireEvent.click(option)
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }))

    await waitFor(() => expect(screen.getByText('✓ 已完成')).toBeTruthy())
    expect(answerRequestHeaders?.get('idempotency-key')).toBe('idem-1')
    expect(answerRequestHeaders?.get('authorization')).toBe('Bearer token-1')
  })

  it('题目加载失败时展示降级文案', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(500, {
        error: { code: 'INTERNAL', message: 'boom' },
      }),
    )

    render(<QuizCard sessionId="quiz-1" />)

    await waitFor(() => expect(screen.getByText('题目加载失败')).toBeTruthy())
  })
})
