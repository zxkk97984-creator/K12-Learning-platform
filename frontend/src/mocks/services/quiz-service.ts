import type { QuizService } from '@/shared/api/quiz-service'
import type {
  CreateQuizInput,
  HintResult,
  SubmitAnswerInput,
} from '@/shared/api/quiz-service'
import type {
  QuizAnswer,
  QuizInteraction,
  QuizQuestion,
  QuizSession,
} from '@/entities/quiz/types'

import { delay } from '../delay'
import { mockQuizQuestions, mockQuizSessions } from '../data/quizzes'

let quizSessions: QuizSession[] = mockQuizSessions.map((session) => ({ ...session }))
let questions: Record<string, QuizQuestion[]> = {
  q1: mockQuizQuestions.q1.map((question) => ({ ...question })),
}
// 原型 quiz-detail 第 1 题：你的答案 B、正确（Mock 补录，供只读答卷页展示）
let answers: QuizAnswer[] = [
  {
    answer_id: 'ans-q1-q1q1',
    quiz_session_id: 'q1',
    question_id: 'q1q1',
    student_id: 'stu-xiaoming',
    submitted_answer: { key: 'B' },
    is_correct: true,
    attempt_no: 1,
    hint_level_at_submit: 0,
    is_final: true,
    submitted_at: '2026-08-18T00:20:00Z',
    created_at: '2026-08-18T00:20:00Z',
  },
]
let interactions: QuizInteraction[] = []
let hintLevels: Record<string, number> = {}
let interactionSeq = 1

const HINTS: Record<number, string> = {
  1: '先想想：训练数据是让机器背答案，还是让机器从例子中找规律？',
  2: '把“训练数据”想成你教小狗认识球时反复展示的那些例子。',
  3: '选出那个描述“从例子里发现可重复规律”的选项。',
}

function nowIso(): string {
  return new Date().toISOString()
}

export class MockQuizService implements QuizService {
  async getQuizSessions() {
    return delay(quizSessions.map((session) => ({ ...session })), 200)
  }

  async getQuizSession(quizSessionId: string) {
    const session = quizSessions.find((item) => item.quiz_session_id === quizSessionId)
    if (!session) throw new Error(`QUIZ_NOT_FOUND: ${quizSessionId}`)
    return delay({ ...session }, 200)
  }

  async createQuizSession(input?: CreateQuizInput) {
    const liveCount = quizSessions.filter((session) =>
      session.quiz_session_id.startsWith('q-live'),
    ).length
    const quizSessionId = liveCount === 0 ? 'q-live' : `q-live-${liveCount + 1}`
    const now = nowIso()
    const session: QuizSession = {
      quiz_session_id: quizSessionId,
      student_id: 'stu-xiaoming',
      conversation_id: input?.conversation_id ?? 'conv-1',
      teacher_role_id: 'role-shuangling',
      book_id: input?.book_id ?? 'b1',
      chapter_id: input?.chapter_id ?? 'ch3',
      title: '训练数据 · 随堂测验',
      quiz_kind: input?.quiz_kind ?? 'AI_QUIZ',
      status: 'ACTIVE',
      result_summary: null,
      ai_feedback: null,
      skill_version: 'quiz-v1',
      created_at: now,
      updated_at: now,
      completed_at: null,
    }
    const source = mockQuizQuestions.q1[0]
    questions[quizSessionId] = [
      {
        ...source,
        question_id: `${quizSessionId}q1`,
        quiz_session_id: quizSessionId,
      },
    ]
    quizSessions = [...quizSessions, session]
    return delay({ ...session }, 300)
  }

  async getQuestions(quizSessionId: string) {
    return delay((questions[quizSessionId] ?? []).map((question) => ({ ...question })), 200)
  }

  async submitAnswer(
    quizSessionId: string,
    questionId: string,
    input: SubmitAnswerInput,
    _idempotencyKey?: string,
  ) {
    const session = quizSessions.find((item) => item.quiz_session_id === quizSessionId)
    if (!session) throw new Error(`QUIZ_NOT_FOUND: ${quizSessionId}`)
    const question = (questions[quizSessionId] ?? []).find(
      (item) => item.question_id === questionId,
    )
    if (!question) throw new Error(`QUESTION_NOT_FOUND: ${questionId}`)

    const isCorrect = String(question.correct_answer.key) === String(input.answer.key)
    const attemptNo =
      answers.filter(
        (item) => item.quiz_session_id === quizSessionId && item.question_id === questionId,
      ).length + 1
    const hintLevel = input.hint_level_at_submit ?? hintLevels[questionId] ?? 0
    const answer: QuizAnswer = {
      answer_id: `ans-${quizSessionId}-${questionId}-${attemptNo}`,
      quiz_session_id: quizSessionId,
      question_id: questionId,
      student_id: 'stu-xiaoming',
      submitted_answer: input.answer,
      is_correct: isCorrect,
      attempt_no: attemptNo,
      hint_level_at_submit: hintLevel,
      is_final: isCorrect,
      submitted_at: nowIso(),
      created_at: nowIso(),
    }
    answers = [...answers, answer]
    interactions = [
      ...interactions,
      {
        interaction_id: `it-${interactionSeq}`,
        quiz_session_id: quizSessionId,
        question_id: questionId,
        interaction_type: 'ANSWER_SUBMIT',
        payload: { submitted_answer: input.answer },
        message_id: null,
        answer_id: answer.answer_id,
        sequence: interactionSeq,
        created_at: nowIso(),
      },
    ]
    interactionSeq += 1
    interactions = [
      ...interactions,
      {
        interaction_id: `it-${interactionSeq}`,
        quiz_session_id: quizSessionId,
        question_id: questionId,
        interaction_type: 'ANSWER_RESULT',
        payload: { is_correct: isCorrect },
        message_id: null,
        answer_id: answer.answer_id,
        sequence: interactionSeq,
        created_at: nowIso(),
      },
    ]
    interactionSeq += 1

    if (isCorrect) {
      quizSessions = quizSessions.map((item) =>
        item.quiz_session_id === quizSessionId
          ? {
              ...item,
              status: 'COMPLETED',
              result_summary: {
                correct: 1,
                total: (questions[quizSessionId] ?? []).length,
                hints_used: hintLevel,
              },
              ai_feedback: '一次答对，概念和例子连得很好。',
              completed_at: nowIso(),
              updated_at: nowIso(),
            }
          : item,
      )
    }
    return delay({ ...answer }, 200)
  }

  async requestHint(quizSessionId: string, questionId: string) {
    const question = (questions[quizSessionId] ?? []).find(
      (item) => item.question_id === questionId,
    )
    if (!question) throw new Error(`QUESTION_NOT_FOUND: ${questionId}`)
    const maxHintLevel = question.interaction_policy.max_hint_level
    const level = (hintLevels[questionId] ?? 0) + 1
    if (level > maxHintLevel) throw new Error('QUIZ_HINT_LIMIT_REACHED')
    hintLevels = { ...hintLevels, [questionId]: level }
    interactions = [
      ...interactions,
      {
        interaction_id: `it-${interactionSeq}`,
        quiz_session_id: quizSessionId,
        question_id: questionId,
        interaction_type: 'HINT_REQUEST',
        payload: { hint_level: level },
        message_id: null,
        answer_id: null,
        sequence: interactionSeq,
        created_at: nowIso(),
      },
    ]
    interactionSeq += 1
    interactions = [
      ...interactions,
      {
        interaction_id: `it-${interactionSeq}`,
        quiz_session_id: quizSessionId,
        question_id: questionId,
        interaction_type: 'HINT_RESPONSE',
        payload: { hint_level: level, hint_text: HINTS[level] },
        message_id: null,
        answer_id: null,
        sequence: interactionSeq,
        created_at: nowIso(),
      },
    ]
    interactionSeq += 1
    const result: HintResult = {
      hint_level: level,
      hint_text: HINTS[level],
      max_hint_level: maxHintLevel,
    }
    return delay(result, 200)
  }

  async getAnswers(quizSessionId: string) {
    return delay(answers.filter((item) => item.quiz_session_id === quizSessionId), 150)
  }

  async getInteractions(quizSessionId: string) {
    return delay(interactions.filter((item) => item.quiz_session_id === quizSessionId), 150)
  }
}
