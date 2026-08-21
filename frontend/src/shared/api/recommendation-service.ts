export type RecommendationType = 'CONTINUE_READING' | 'REVIEW_WEAK' | 'READ_NEXT'

export interface Recommendation {
  recommendation_id: string
  recommendation_type: RecommendationType
  title: string
  description: string
  reason: string
  evidence_ids: string[]
  related_book_id: string | null
  status: 'ACTIVE' | 'DISMISSED'
  created_at: string
  updated_at: string
}

export interface RecommendationService {
  getRecommendations(): Promise<Recommendation[]>
  dismissRecommendation(recommendationId: string): Promise<Recommendation>
}
