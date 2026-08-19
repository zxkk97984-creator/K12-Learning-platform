import type { StudentPreference, StudentProfile } from '@/entities/student/types'
import { deriveStage } from '@/entities/student/types'

/** 原型学生画像（小明 / 初二·8 年级 / example_based / medium / short） */
export const mockStudentProfile: StudentProfile = {
  student_id: 'stu-xiaoming',
  nickname: '小明',
  avatar_url: null,
  grade: 8,
  stage: deriveStage(8),
  language: 'zh-CN',
  learning_goal: null,
  current_teacher_role_id: 'role-shuangling',
  learning_days: 0,
  total_learning_minutes: 0,
  completed_books: 0,
  completed_chapters: 2,
  quiz_count: 3,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-18T20:18:00Z',
}

/** 原型 frontmatter：preferred_explanation_style=example_based / difficulty=medium / session_length=short */
export const mockStudentPreference: StudentPreference = {
  preference_id: 'pref-xiaoming',
  student_id: 'stu-xiaoming',
  preferred_explanation_style: 'EXAMPLE_BASED',
  preferred_difficulty: 'MEDIUM',
  preferred_session_length: 'SHORT',
  voice_preference: { input_enabled: false, tts_enabled: false, volume: 0.8, speed: 1 },
  active_questioning_enabled: true,
  daily_learning_minutes: 30,
  evidence_ids: ['ev-1', 'ev-2'],
  updated_at: '2026-08-18T20:18:00Z',
}
