import { describe, expect, it } from 'vitest'

import { MockQuizService } from './quiz-service'

describe('MockQuizService', () => {
  const quizService = new MockQuizService()
  it('初始 3 条测验，createQuizSession 生成 q-live', async () => {
    expect(await quizService.getQuizSessions()).toHaveLength(3)
    const created = await quizService.createQuizSession({ quiz_kind: 'AI_QUIZ' })
    expect(created.quiz_session_id).toBe('q-live')
    expect(created.status).toBe('ACTIVE')
    expect((await quizService.getQuizSessions()).length).toBe(4)
  })

  it('submitAnswer：正确答案 B 判定 + 会话落 COMPLETED', async () => {
    const questions = await quizService.getQuestions('q-live')
    expect(questions).toHaveLength(1)
    const answer = await quizService.submitAnswer('q-live', 'q-liveq1', {
      answer: { key: 'B' },
      hint_level_at_submit: 0,
    })
    expect(answer.is_correct).toBe(true)
    expect(answer.attempt_no).toBe(1)
    expect(answer.is_final).toBe(true)
    const session = await quizService.getQuizSession('q-live')
    expect(session.status).toBe('COMPLETED')
    expect(session.result_summary).toEqual({ correct: 1, total: 1, hints_used: 0 })
  })

  it('submitAnswer：错误答案 is_correct=false 且不置 final', async () => {
    const created = await quizService.createQuizSession({ quiz_kind: 'AI_QUIZ' })
    const wrong = await quizService.submitAnswer(created.quiz_session_id, `${created.quiz_session_id}q1`, {
      answer: { key: 'A' },
    })
    expect(wrong.is_correct).toBe(false)
    expect(wrong.is_final).toBe(false)
  })

  it('requestHint：三级递增，第 4 次抛 QUIZ_HINT_LIMIT_REACHED', async () => {
    const created = await quizService.createQuizSession({ quiz_kind: 'AI_QUIZ' })
    const questionId = `${created.quiz_session_id}q1`
    expect((await quizService.requestHint(created.quiz_session_id, questionId)).hint_level).toBe(1)
    expect((await quizService.requestHint(created.quiz_session_id, questionId)).hint_level).toBe(2)
    expect((await quizService.requestHint(created.quiz_session_id, questionId)).hint_level).toBe(3)
    await expect(quizService.requestHint(created.quiz_session_id, questionId)).rejects.toThrow(
      'QUIZ_HINT_LIMIT_REACHED',
    )
  })
})
