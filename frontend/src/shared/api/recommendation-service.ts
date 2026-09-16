export type RecommendationType =
  | 'CONTINUE_READING'
  | 'REVIEW_WEAK'
  | 'READ_NEXT'
  | 'INTEREST_MATCH'

export interface Recommendation {
  recommendation_id: string
  recommendation_type: RecommendationType
  title: string
  description: string
  reason: string
  evidence_ids: string[]
  related_book_id: string | null
  source_ids?: string[]
  license?: string | null
  source_url?: string | null
  model_info?: Record<string, unknown> | null
  skill_version?: string | null
  expires_at?: string | null
  status: 'ACTIVE' | 'DISMISSED' | 'EXPIRED'
  created_at: string
  updated_at: string
}

export type LearningNextType =
  | 'CONTINUE_QUIZ'
  | 'REVIEW_QUIZ'
  | 'NEXT_CHAPTER'
  | 'CONTINUE_READING'
  | 'START_BOOK'

export interface LearningNextAction {
  type: LearningNextType
  label: string
  book_id: string | null
  chapter_id: string | null
  quiz_session_id: string | null
  reason: string
  evidence_ids: string[]
}

export interface RecommendationService {
  getRecommendations(): Promise<Recommendation[]>
  dismissRecommendation(recommendationId: string): Promise<Recommendation>
  getLearningNext(): Promise<LearningNextAction>
}
