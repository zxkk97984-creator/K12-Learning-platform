import type { StudentPreference, StudentProfile } from '@/entities/student/types'

export type StudentProfilePatch = Partial<
  Pick<
    StudentProfile,
    'nickname' | 'avatar_url' | 'grade' | 'language' | 'learning_goal' | 'current_teacher_role_id'
  >
>

export type StudentPreferencePatch = Partial<
  Omit<StudentPreference, 'preference_id' | 'student_id' | 'evidence_ids' | 'updated_at'>
>

export interface StudentService {
  getMe(): Promise<StudentProfile>
  updateMe(patch: StudentProfilePatch): Promise<StudentProfile>
  getPreferences(): Promise<StudentPreference>
  updatePreferences(patch: StudentPreferencePatch): Promise<StudentPreference>
}
