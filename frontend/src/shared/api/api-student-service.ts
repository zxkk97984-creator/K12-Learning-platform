import type {
  AuthDTO,
  StudentPreference,
  StudentProfile,
  TeacherRoleDTO,
} from '@/entities/student/types'

import { clearToken, getToken, setToken } from './auth'
import { API_BASE, ApiError, apiRequest } from './http'
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

  getTeacherRoles(): Promise<TeacherRoleDTO[]> {
    return apiRequest<TeacherRoleDTO[]>('/teacher-roles?enabled=true')
  }

  async uploadAvatar(file: File): Promise<StudentProfile> {
    const form = new FormData()
    form.append('file', file)
    const token = getToken()
    const response = await fetch(`${API_BASE}/me/avatar`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: form,
    })
    const payload: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      const error = (payload as { error?: { code?: string; message?: string } })?.error
      throw new ApiError(
        response.status,
        error?.code ?? 'HTTP_ERROR',
        error?.message ?? `HTTP ${response.status}`,
      )
    }
    return (payload as { data: StudentProfile }).data
  }
}
