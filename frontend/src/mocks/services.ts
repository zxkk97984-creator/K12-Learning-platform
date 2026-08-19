import type { StudentService } from '@/shared/api/student-service'
import type { ContentService } from '@/shared/api/content-service'
import type { ConversationService } from '@/shared/api/conversation-service'
import type { QuizService } from '@/shared/api/quiz-service'
import type { MemoryService } from '@/shared/api/memory-service'
import type { TeacherRoleService } from '@/shared/api/teacher-role-service'

import { MockStudentService } from './services/student-service'
import { MockContentService } from './services/content-service'
import { MockConversationService } from './services/conversation-service'
import { MockQuizService } from './services/quiz-service'
import { MockMemoryService } from './services/memory-service'
import { MockTeacherRoleService } from './services/teacher-role-service'

/**
 * 统一 Mock Service 注册表（总控 §10.5 / §27）。
 * 替换边界：Phase 2 起逐个把实例替换为 ApiXxxService（接口不变，只改这里）。
 * Mock 直接返回领域数据（0-D 信封 { data, meta } 由未来 Api 实现内部解包）。
 */
export const studentService: StudentService = new MockStudentService()
export const contentService: ContentService = new MockContentService()
export const conversationService: ConversationService = new MockConversationService()
export const quizService: QuizService = new MockQuizService()
export const memoryService: MemoryService = new MockMemoryService()
export const teacherRoleService: TeacherRoleService = new MockTeacherRoleService()
