import type { StudentService } from '@/shared/api/student-service'
import type { ContentService } from '@/shared/api/content-service'
import type { ConversationService } from '@/shared/api/conversation-service'
import type { QuizService } from '@/shared/api/quiz-service'
import type { MemoryService } from '@/shared/api/memory-service'

import { ApiStudentService } from '@/shared/api/api-student-service'
import { ApiContentService } from '@/shared/api/api-content-service'
import { ApiConversationService } from '@/shared/api/api-conversation-service'
import { ApiMemoryService } from '@/shared/api/api-memory-service'
import { ApiQuizService } from '@/shared/api/api-quiz-service'
import { ApiRecommendationService } from '@/shared/api/api-recommendation'
import type { RecommendationService } from '@/shared/api/recommendation-service'


/**
 * 统一 Service 注册表（总控 §10.5 / §27）。
 * 替换边界：Phase 2 起逐个把实例替换为 ApiXxxService（接口不变，只改这里）。
 * 2-D：StudentService 已切真实后端；3-D：ContentService 已切真实后端；4-D：ConversationService 已切真实后端；4-E：MemoryService 已切真实后端；5-C：QuizService 已切真实后端。
 */
export const studentService: StudentService = new ApiStudentService()
export const contentService: ContentService = new ApiContentService()
export const conversationService: ConversationService = new ApiConversationService()
export const quizService: QuizService = new ApiQuizService()
export const memoryService: MemoryService = new ApiMemoryService()
export const recommendationService: RecommendationService = new ApiRecommendationService()
