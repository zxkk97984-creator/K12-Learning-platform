import type {
  LearningNextAction,
  Recommendation,
  RecommendationService,
} from './recommendation-service'
import { apiRequest } from './http'

/** 规则推荐客户端；推荐生成由后端惰性完成，前端只消费 ACTIVE 列表。 */
export class ApiRecommendationService implements RecommendationService {
  getRecommendations(): Promise<Recommendation[]> {
    return apiRequest<Recommendation[]>('/me/recommendations')
  }

  dismissRecommendation(recommendationId: string): Promise<Recommendation> {
    return apiRequest<Recommendation>(
      `/me/recommendations/${encodeURIComponent(recommendationId)}/dismiss`,
      { method: 'POST' },
    )
  }

  getLearningNext(): Promise<LearningNextAction> {
    return apiRequest<LearningNextAction>('/me/learning-next')
  }
}
