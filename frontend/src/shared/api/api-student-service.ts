import type { AuthDTO, StudentPreference, StudentProfile } from '@/entities/student/types'

import { clearToken, setToken } from './auth'
import { apiRequest } from './http'
import type {
  StudentPreferencePatch,
  StudentProfilePatch,
  StudentService,
} from './student-service'

/** 真实后端 Identity/Student 客户端（2-D；其余 Service 仍 Mock，总控 §27） */
export class ApiStudentService implements StudentService {
  async login(username: string, password: string): Promise<AuthDTO> {
    const dto = await apiRequest<AuthDTO>('/auth/login', {
      method: 'POST',
      body: { username, password },
    })
    setToken(dto.access_token)
    return dto
  }

  async logout(): Promise<void> {
    try {
      await apiRequest<void>('/auth/logout', { method: 'POST' })
    } finally {
      clearToken()
    }
  }

  getMe(): Promise<StudentProfile> {
    return apiRequest<StudentProfile>('/me')
  }

  updateMe(patch: StudentProfilePatch): Promise<StudentProfile> {
    return apiRequest<StudentProfile>('/me', { method: 'PATCH', body: patch })
  }

  getPreferences(): Promise<StudentPreference> {
    return apiRequest<StudentPreference>('/me/preferences')
  }

  updatePreferences(patch: StudentPreferencePatch): Promise<StudentPreference> {
    return apiRequest<StudentPreference>('/me/preferences', {
      method: 'PATCH',
      body: patch,
    })
  }
}
