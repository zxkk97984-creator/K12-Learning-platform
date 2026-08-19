import type { StudentService } from '@/shared/api/student-service'
import type {
  StudentPreferencePatch,
  StudentProfilePatch,
} from '@/shared/api/student-service'
import { deriveStage } from '@/entities/student/types'

import { delay } from '../delay'
import { mockStudentPreference, mockStudentProfile } from '../data/student'

let profile = { ...mockStudentProfile }
let preference = { ...mockStudentPreference }

export class MockStudentService implements StudentService {
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
}
