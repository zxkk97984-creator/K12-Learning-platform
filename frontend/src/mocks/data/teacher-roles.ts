import type { TeacherRole } from '@/entities/student/types'

/** 原型 spriteFrames（row/frames/label 一一对应） */
export const spriteFrames = {
  idle: { row: 0, frames: 6, label: '待机中' },
  'running-right': { row: 1, frames: 8, label: '向右移动中' },
  'running-left': { row: 2, frames: 8, label: '向左移动中' },
  listening: { row: 6, frames: 6, label: '正在听' },
  thinking: { row: 8, frames: 6, label: '思考中' },
  speaking: { row: 3, frames: 4, label: '讲解中' },
  happy: { row: 4, frames: 5, label: '很开心' },
  confused: { row: 5, frames: 8, label: '有点疑惑' },
  encouraging: { row: 7, frames: 6, label: '给你鼓励' },
} as const

export type SpriteState = keyof typeof spriteFrames

/** 首发角色霜铃；persona/grade_rules 细节由 Phase 11 Persona 管理填充 */
export const mockTeacherRoles: TeacherRole[] = [
  {
    role_id: 'role-shuangling',
    name: '霜铃',
    description: 'K12 AI 数字教师首发角色',
    persona: { base_persona: '', character_persona: '' },
    tone: null,
    teaching_style: null,
    avatar: null,
    sprite_manifest: {
      sheet_url: '/spritesheet-extended.webp',
      grid_cols: 8,
      grid_rows: 11,
      states: spriteFrames,
    },
    voice_id: null,
    grade_rules: {
      primary: { fs_body: '17px' },
      junior: {},
      senior: { fs_body: '14px' },
    },
    enabled: true,
    version: 1,
  },
]
