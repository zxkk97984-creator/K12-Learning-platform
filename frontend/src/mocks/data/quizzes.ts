import type { QuizQuestion, QuizSession } from '@/entities/quiz/types'

/**
 * 原型 QUIZZES（3 条初始）映射：
 * date → created_at（展示日期由 created_at 派生）
 * type 章节测验/AI 小测 → quiz_kind CHAPTER_QUIZ/AI_QUIZ
 * score「8 / 10」→ result_summary { correct: 8, total: 10 }
 * meta「使用 1 次提示 · 3 道应用题」→ result_summary.hints_used / total
 * note → ai_feedback；term 为原型占位字段，0-D 已废弃，不保留
 */
export const mockQuizSessions: QuizSession[] = [
  {
    quiz_session_id: 'q1',
    student_id: 'stu-xiaoming',
    conversation_id: 'conv-1',
    teacher_role_id: 'role-shuangling',
    book_id: 'b1',
    chapter_id: 'ch3',
    title: '机器学习基础小测',
    quiz_kind: 'CHAPTER_QUIZ',
    status: 'COMPLETED',
    result_summary: { correct: 8, total: 10, hints_used: 1 },
    ai_feedback: '概念题表现稳定，应用题还需要多练。',
    skill_version: 'quiz-v1',
    created_at: '2026-08-18T00:00:00Z',
    updated_at: '2026-08-18T00:30:00Z',
    completed_at: '2026-08-18T00:30:00Z',
  },
  {
    quiz_session_id: 'q2',
    student_id: 'stu-xiaoming',
    conversation_id: 'conv-1',
    teacher_role_id: 'role-shuangling',
    book_id: 'b1',
    chapter_id: 'ch2',
    title: '推荐系统与兴趣',
    quiz_kind: 'AI_QUIZ',
    status: 'COMPLETED',
    result_summary: { correct: 7, total: 10, hints_used: 0 },
    ai_feedback: '你能说出推荐的原因，但还会忽略数据来源。',
    skill_version: 'quiz-v1',
    created_at: '2026-08-15T00:00:00Z',
    updated_at: '2026-08-15T00:20:00Z',
    completed_at: '2026-08-15T00:20:00Z',
  },
  {
    quiz_session_id: 'q3',
    student_id: 'stu-xiaoming',
    conversation_id: 'conv-1',
    teacher_role_id: 'role-shuangling',
    book_id: 'b1',
    chapter_id: 'ch1',
    title: '什么是机器学习',
    quiz_kind: 'AI_QUIZ',
    status: 'COMPLETED',
    result_summary: { correct: 6, total: 10, hints_used: 2 },
    ai_feedback: '概念记住了，但例子和概念还连不起来。',
    skill_version: 'quiz-v1',
    created_at: '2026-08-11T00:00:00Z',
    updated_at: '2026-08-11T00:25:00Z',
    completed_at: '2026-08-11T00:25:00Z',
  },
]

/**
 * 题目来自原型 quiz-card（题干/选项完整）与 quiz-detail（解析）。
 * 原型 quiz-detail 的 q2/q3 选项不完整，为不编造数据，仅收录完整已知题；
 * q-live 由 MockQuizService.createQuizSession 生成并复用本题。
 */
export const mockQuizQuestions: Record<string, QuizQuestion[]> = {
  q1: [
    {
      question_id: 'q1q1',
      quiz_session_id: 'q1',
      question_order: 1,
      question_type: 'SINGLE_CHOICE',
      stem: '训练数据最重要的作用是什么？',
      options: [
        { key: 'A', text: '只要数据越多，结果就一定正确' },
        { key: 'B', text: '让机器从例子中发现可重复的规律' },
        { key: 'C', text: '让机器不需要再看新的内容' },
        { key: 'D', text: '让机器不用验证就直接做决定' },
      ],
      correct_answer: { key: 'B' },
      explanation:
        '训练数据的价值，不是数量本身，而是它能不能帮助机器发现可重复的规律。',
      source_context: { book_id: 'b1', chapter_id: 'ch3', knowledge_points: ['training_data'] },
      interaction_policy: { allow_hint: true, max_hint_level: 3 },
      knowledge_point_ids: ['kp-training-data'],
    },
  ],
}
