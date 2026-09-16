import type {
  LearningNextAction,
  Recommendation,
  RecommendationService,
} from '@/shared/api/recommendation-service'

/** 测试/离线替身；生产注册表使用 ApiRecommendationService。 */
export class MockRecommendationService implements RecommendationService {
  private recommendations: Recommendation[] = []

  getRecommendations(): Promise<Recommendation[]> {
    return Promise.resolve(this.recommendations)
  }

  dismissRecommendation(recommendationId: string): Promise<Recommendation> {
    const recommendation = this.recommendations.find(
      (item) => item.recommendation_id === recommendationId,
    )
    if (!recommendation) {
      return Promise.reject(new Error('recommendation not found'))
    }
    const dismissed = { ...recommendation, status: 'DISMISSED' as const }
    this.recommendations = this.recommendations.filter(
      (item) => item.recommendation_id !== recommendationId,
    )
    return Promise.resolve(dismissed)
  }

  getLearningNext(): Promise<LearningNextAction> {
    return Promise.resolve({
      type: 'START_BOOK',
      label: '从《人工智能初探》开始',
      book_id: null,
      chapter_id: null,
      quiz_session_id: null,
      reason: '先挑一本适合的书开始学习。',
      evidence_ids: [],
    })
  }
}
