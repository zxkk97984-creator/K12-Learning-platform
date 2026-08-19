// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
  updateMe: vi.fn(),
  getTeacherRoles: vi.fn(),
  getRoles: vi.fn(),
  refreshMe: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/mocks/services', () => ({
  studentService: {
    getPreferences: mocks.getPreferences,
    updatePreferences: mocks.updatePreferences,
    updateMe: mocks.updateMe,
    getTeacherRoles: mocks.getTeacherRoles,
  },
  teacherRoleService: { getRoles: mocks.getRoles },
}))

vi.mock('@/features/auth', () => {
  const currentUser = {
      student_id: 'student-1',
      nickname: '小明',
      avatar_url: null,
      grade: 8,
      stage: 'JUNIOR',
      language: 'zh-CN',
      learning_goal: null,
      current_teacher_role_id: null,
      learning_days: 1,
      total_learning_minutes: 30,
      completed_books: 0,
      completed_chapters: 0,
      quiz_count: 0,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-19T00:00:00Z',
  }
  return {
    useAuth: () => ({ currentUser, refreshMe: mocks.refreshMe }),
  }
})

vi.mock('@/features/feedback', () => ({
  useToastStore: (selector: (state: unknown) => unknown) =>
    selector({ showToast: mocks.showToast }),
}))

import SettingsPage from './SettingsPage'

const roles = [
  {
    role_id: 'role-slang',
    name: 'shuangling',
    description: '默认教师',
    tone: '温暖',
    teaching_style: '引导',
    avatar: null,
    voice_id: null,
    enabled: true,
  },
  {
    role_id: 'role-strict',
    name: 'strict-mentor',
    description: '严谨导师',
    tone: '严谨',
    teaching_style: '逻辑',
    avatar: null,
    voice_id: null,
    enabled: true,
  },
]

describe('SettingsPage teacher roles', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPreferences.mockResolvedValue({
      preference_id: 'pref-1',
      student_id: 'student-1',
      preferred_explanation_style: 'EXAMPLE_BASED',
      preferred_difficulty: 'MEDIUM',
      preferred_session_length: 'SHORT',
      voice_preference: { input_enabled: true, tts_enabled: true, volume: 0.8, speed: 1 },
      active_questioning_enabled: true,
      daily_learning_minutes: 30,
      evidence_ids: [],
      updated_at: '2026-08-19T00:00:00Z',
    })
    mocks.getRoles.mockResolvedValue([])
    mocks.getTeacherRoles.mockResolvedValue(roles)
    mocks.updateMe.mockResolvedValue({})
  })

  afterEach(() => cleanup())

  it('渲染角色卡片并可切换', async () => {
    render(React.createElement(SettingsPage))

    await waitFor(() => expect(screen.getByText('strict-mentor')).toBeTruthy())
    fireEvent.click(screen.getByText('strict-mentor'))

    await waitFor(() =>
      expect(mocks.updateMe).toHaveBeenCalledWith({
        current_teacher_role_id: 'role-strict',
      }),
    )
    expect(mocks.refreshMe).toHaveBeenCalled()
  })
})
