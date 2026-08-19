// 学生域类型（对齐 0-C Domain Model，字段按前端需要精简）

export type Stage = 'PRIMARY' | 'JUNIOR' | 'SENIOR'

/** grade 1~12 → 学段（派生，不落库；展示字符串由渲染层生成） */
export function deriveStage(grade: number): Stage {
  if (grade >= 1 && grade <= 6) return 'PRIMARY'
  if (grade >= 7 && grade <= 9) return 'JUNIOR'
  return 'SENIOR'
}

export interface StudentProfile {
  student_id: string
  nickname: string
  avatar_url: string | null
  /** 1~12（0-C：禁止用「初二 · 8 年级」这类展示字符串存储） */
  grade: number
  /** (derived) 由 grade 派生 */
  stage: Stage
  language: string
  learning_goal: string | null
  current_teacher_role_id: string | null
  /** 统计摘要（Worker 重算缓存，0-C） */
  learning_days: number
  total_learning_minutes: number
  completed_books: number
  completed_chapters: number
  quiz_count: number
  created_at: string
  updated_at: string
}

export interface AuthUser {
  user_id: string
  username: string
  user_type: 'STUDENT' | 'ADMIN'
}

/** 0-D AuthDTO */
export interface AuthDTO {
  access_token: string
  token_type: string
  expires_at: string
  user: AuthUser
}

export type PreferredExplanationStyle =
  | 'EXAMPLE_BASED'
  | 'VISUAL'
  | 'STORY'
  | 'DIRECT_DEFINITION'
  | 'STEP_BY_STEP'
  | 'CODE'
  | 'INTERACTIVE'

export type PreferredDifficulty = 'EASY' | 'MEDIUM' | 'HARD'
export type PreferredSessionLength = 'SHORT' | 'MEDIUM' | 'LONG'

export interface VoicePreference {
  input_enabled: boolean
  tts_enabled: boolean
  volume: number
  speed: number
}

export interface StudentPreference {
  preference_id: string
  student_id: string
  preferred_explanation_style: PreferredExplanationStyle
  preferred_difficulty: PreferredDifficulty
  preferred_session_length: PreferredSessionLength
  voice_preference: VoicePreference
  active_questioning_enabled: boolean
  daily_learning_minutes: number
  /** jsonb 引用（0-E：非物理 FK） */
  evidence_ids: string[]
  updated_at: string
}

export interface TeacherRole {
  role_id: string
  name: string
  description: string | null
  persona: Record<string, unknown>
  tone: string | null
  teaching_style: string | null
  avatar: string | null
  /** 0-B spritesheet 契约：{ sheet_url, grid_cols, grid_rows, states } */
  sprite_manifest: Record<string, unknown> | null
  voice_id: string | null
  /** 学段适配：{ primary, junior, senior } */
  grade_rules: Record<string, unknown>
  enabled: boolean
  version: number
}

/** 学生端可见的 TeacherRole 展示字段（11-A：不含 persona/sprite/grade_rules 内部配置） */
export interface TeacherRoleDTO {
  role_id: string
  name: string
  description: string | null
  tone: string
  teaching_style: string
  avatar: string | null
  voice_id: string | null
  enabled: boolean
}
