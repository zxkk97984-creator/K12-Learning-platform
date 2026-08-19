import type { StudentService } from '@/shared/api/student-service'
import type {
  StudentPreferencePatch,
  StudentProfilePatch,
} from '@/shared/api/student-service'
import type { AuthDTO, TeacherRoleDTO } from '@/entities/student/types'
import { deriveStage } from '@/entities/student/types'

import { delay } from '../delay'
import { mockStudentPreference, mockStudentProfile } from '../data/student'

let profile = { ...mockStudentProfile }
let preference = { ...mockStudentPreference }

export class MockStudentService implements StudentService {
  async login(username: string, password: string): Promise<AuthDTO> {
    if (username !== 'xiaoming' || password !== 'demo123') {
      throw new Error('INVALID_CREDENTIALS')
    }
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
    return {
      access_token: 'mock-access-token',
      token_type: 'Bearer',
      expires_at: expiresAt,
      user: { user_id: 'stu-xiaoming', username: 'xiaoming', user_type: 'STUDENT' },
    }
  }

  async logout(): Promise<void> {
    // Mock 无服务端状态（与 0-D MVP 语义一致）
  }

  async getMe() {
    return delay({ ...profile }, 150)
  }

  async updateMe(patch: StudentProfilePatch) {
    const grade = patch.grade ?? profile.grade
    profile = {
      ...profile,
      ...patch,
      grade,
      stage: deriveStage(grade),
      updated_at: new Date().toISOString(),
    }
    return delay({ ...profile }, 150)
  }

  async getPreferences() {
    return delay({ ...preference }, 150)
  }

  async updatePreferences(patch: StudentPreferencePatch) {
    preference = { ...preference, ...patch, updated_at: new Date().toISOString() }
    return delay({ ...preference }, 150)
  }

  async getTeacherRoles(): Promise<TeacherRoleDTO[]> {
    return delay(
      [
        {
          role_id: '00000000-0000-0000-0000-000000000001',
          name: 'shuangling',
          description: '默认 AI 教师',
          tone: '温暖、鼓励',
          teaching_style: '从生活例子出发，逐步引导',
          avatar: null,
          voice_id: null,
          enabled: true,
        },
        {
          role_id: '00000000-0000-0000-0000-000000000002',
          name: 'strict-mentor',
          description: '严谨导师',
          tone: '严谨、清晰',
          teaching_style: '强调逻辑与证据',
          avatar: null,
          voice_id: null,
          enabled: true,
        },
      ],
      150,
    )
  }
}
