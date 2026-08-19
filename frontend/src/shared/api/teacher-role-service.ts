import type { TeacherRole } from '@/entities/student/types'

export interface TeacherRoleService {
  getRoles(): Promise<TeacherRole[]>
  getRole(roleId: string): Promise<TeacherRole>
}
