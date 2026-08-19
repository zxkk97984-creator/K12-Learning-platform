import type { StudentService } from '@/shared/api/student-service'
import type { ContentService } from '@/shared/api/content-service'
import type { ConversationService } from '@/shared/api/conversation-service'
import type { QuizService } from '@/shared/api/quiz-service'
import type { MemoryService } from '@/shared/api/memory-service'
import type { TeacherRoleService } from '@/shared/api/teacher-role-service'

import { ApiStudentService } from '@/shared/api/api-student-service'
import { ApiContentService } from '@/shared/api/api-content-service'
import { ApiConversationService } from '@/shared/api/api-conversation-service'

import { MockQuizService } from './services/quiz-service'
import { MockMemoryService } from './services/memory-service'
import { MockTeacherRoleService } from './services/teacher-role-service'

/**
 * 统一 Service 注册表（总控 §10.5 / §27）。
 * 替换边界：Phase 2 起逐个把实例替换为 ApiXxxService（接口不变，只改这里）。
 * 2-D：StudentService 已切真实后端；3-D：ContentService 已切真实后端；4-D：ConversationService 已切真实后端；其余业务 Service 保持 Mock。
 */
export const studentService: StudentService = new ApiStudentService()
export const contentService: ContentService = new ApiContentService()
export const conversationService: ConversationService = new ApiConversationService()
export const quizService: QuizService = new MockQuizService()
export const memoryService: MemoryService = new MockMemoryService()
export const teacherRoleService: TeacherRoleService = new MockTeacherRoleService()
