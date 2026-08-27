// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
  updateMe: vi.fn(),
  getTeacherRoles: vi.fn(),
  uploadAvatar: vi.fn(),
  refreshMe: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
  studentService: {
    getPreferences: mocks.getPreferences,
    updatePreferences: mocks.updatePreferences,
    updateMe: mocks.updateMe,
    getTeacherRoles: mocks.getTeacherRoles,
    uploadAvatar: mocks.uploadAvatar,
  },
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
import { useCompanionStore } from '@/features/companion'

const roles = [
  {
    role_id: '00000000-0000-0000-0000-000000000001',
    name: '温暖鼓励',
    description: '以鼓励和引导为主的教学风格',
    tone: '温暖、鼓励',
    teaching_style: '从生活例子出发，逐步引导',
    avatar: null,
    voice_id: null,
    enabled: true,
  },
  {
    role_id: '00000000-0000-0000-0000-000000000002',
    name: '严谨清晰',
    description: '以逻辑和证据为主的教学风格',
    tone: '严谨、清晰',
    teaching_style: '强调逻辑与证据',
    avatar: null,
    voice_id: null,
    enabled: true,
  },
]

describe('SettingsPage teacher roles', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    useCompanionStore.setState({ selectedPetId: 'shuangling' })
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
    mocks.uploadAvatar.mockResolvedValue({})
    mocks.getTeacherRoles.mockResolvedValue(roles)
    mocks.updateMe.mockResolvedValue({})
  })

  afterEach(() => cleanup())

  it('渲染风格卡片并可切换', async () => {
    render(React.createElement(SettingsPage))

    await waitFor(() => expect(screen.getByText('严谨清晰')).toBeTruthy())
    fireEvent.click(screen.getByText('严谨清晰'))

    await waitFor(() =>
      expect(mocks.updateMe).toHaveBeenCalledWith({
        current_teacher_role_id: '00000000-0000-0000-0000-000000000002',
      }),
    )
    expect(mocks.refreshMe).toHaveBeenCalled()
  })

  it('展示六种教师形象并立即保存用户选择', async () => {
    render(React.createElement(SettingsPage))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'AI 教师形象' })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /选择阿尼亚形象/ }))

    expect(useCompanionStore.getState().selectedPetId).toBe('anya')
    expect(window.localStorage.getItem('shuangling-companion-pet')).toBe('anya')
    expect(screen.getByRole('button', { name: /选择阿尼亚形象/ }).getAttribute('aria-pressed')).toBe(
      'true',
    )
  })
})
