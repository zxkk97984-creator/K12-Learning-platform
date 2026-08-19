import type { TeacherRoleService } from '@/shared/api/teacher-role-service'

import { delay } from '../delay'
import { mockTeacherRoles } from '../data/teacher-roles'

export class MockTeacherRoleService implements TeacherRoleService {
  async getRoles() {
    return delay(mockTeacherRoles.map((role) => ({ ...role })), 150)
  }

  async getRole(roleId: string) {
    const role = mockTeacherRoles.find((item) => item.role_id === roleId)
    if (!role) throw new Error(`TEACHER_ROLE_NOT_FOUND: ${roleId}`)
    return delay({ ...role }, 150)
  }
}
