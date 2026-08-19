// 记忆域类型（对齐 0-C；ProfileInsight.level 仅 5 档，总控 §16.4）

export type MemoryType = 'PROFILE' | 'PREFERENCE' | 'LEARNING' | 'EPISODIC'
export type MemoryStatus = 'ACTIVE' | 'DISPUTED' | 'SUPERSEDED' | 'REMOVED'
export type MemoryConfidence = 'LOW' | 'MEDIUM' | 'HIGH'

export interface StudentMemory {
  memory_id: string
  student_id: string
  memory_type: MemoryType
  content: string
  tags: string[]
  confidence: MemoryConfidence
  status: MemoryStatus
  /** jsonb 引用（0-E：非物理 FK） */
  evidence_ids: string[]
  origin_candidate_id: string | null
  user_confirmed: boolean
  created_at: string
  updated_at: string
  confirmed_at: string | null
}

export type ProfileInsightType =
  | 'STRENGTH'
  | 'WEAKNESS'
  | 'UNDERSTANDING'
  | 'HABIT'
  | 'CHANGE'
  | 'INTEREST'

/** 仅允许 5 档（0-C D7 / 总控 §16.4）；禁止百分比/数字 */
export type ProfileInsightLevel = '偏弱' | '一般' | '较稳定' | '较强' | '仍需观察'
export type InsightStatus = 'ACTIVE' | 'SUPERSEDED'

export interface ProfileInsight {
  insight_id: string
  student_id: string
  insight_type: ProfileInsightType
  /** 维度 slug（concept / application_transfer / ai_basics / questioning_habit 等） */
  dimension: string
  level: ProfileInsightLevel
  description: string
  evidence_ids: string[]
  status: InsightStatus
  valid_from: string
  valid_until: string | null
  rule_version: string
  updated_at: string
}

export type EpisodeImportance = 'LOW' | 'MEDIUM' | 'HIGH'

export interface StudentEpisode {
  episode_id: string
  student_id: string
  title: string
  summary: string
  occurred_at: string
  event_ids: string[]
  book_id: string | null
  chapter_id: string | null
  knowledge_point_ids: string[]
  importance: EpisodeImportance
  tags: string[]
  created_at: string
}

export type EvidenceSourceType = 'QUIZ' | 'LEARNING_SESSION' | 'CONVERSATION' | 'BOOK_PROGRESS'

export interface MemoryEvidence {
  evidence_id: string
  student_id: string
  source_type: EvidenceSourceType
  event_ids: string[]
  /** 聚合事实（0-C：只含事实，不含结论） */
  payload: Record<string, unknown>
  count: number
  first_occurred_at: string | null
  last_occurred_at: string | null
  derived_at: string
  rule_version: string
}
