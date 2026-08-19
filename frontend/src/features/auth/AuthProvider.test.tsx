// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { StudentProfile } from '@/entities/student/types'

const loginMock = vi.fn()
const logoutMock = vi.fn()
const getMeMock = vi.fn()

vi.mock('@/mocks/services', () => ({
  studentService: {
    login: loginMock,
    logout: logoutMock,
    getMe: getMeMock,
    updateMe: vi.fn(),
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
  },
}))

import { AuthProvider, useAuth } from './AuthProvider'

const profile: StudentProfile = {
  student_id: 's1',
  nickname: '小明',
  avatar_url: null,
  grade: 8,
  stage: 'JUNIOR',
  language: 'zh-CN',
  learning_goal: null,
  current_teacher_role_id: null,
  learning_days: 0,
  total_learning_minutes: 0,
  completed_books: 0,
  completed_chapters: 0,
  quiz_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
}

function Probe() {
  const { token, currentUser, loading, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="state">
        {loading ? 'loading' : currentUser ? `user:${currentUser.nickname}` : 'anon'}
      </span>
      <span data-testid="token">{token ?? 'none'}</span>
      <button type="button" onClick={() => void login('xiaoming', 'demo123')}>
        login
      </button>
      <button type="button" onClick={() => void logout()}>
        logout
      </button>
    </div>
  )
}

function renderAuth() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('无 token → 未登录态', async () => {
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('anon'))
    expect(screen.getByTestId('token').textContent).toBe('none')
  })

  it('有 token → 初始化拉取 currentUser（刷新保持登录）', async () => {
    window.localStorage.setItem('shuangling-access-token', 'jwt-1')
    getMeMock.mockResolvedValue(profile)
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('user:小明'))
    expect(getMeMock).toHaveBeenCalledTimes(1)
  })

  it('初始化 getMe 401 → 清 token 未登录', async () => {
    window.localStorage.setItem('shuangling-access-token', 'jwt-expired')
    const error = new Error('401') as Error & { status: number }
    error.status = 401
    getMeMock.mockRejectedValue(error)
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('anon'))
    expect(window.localStorage.getItem('shuangling-access-token')).toBeNull()
  })

  it('login 成功 → token + currentUser；logout → 清空', async () => {
    loginMock.mockResolvedValue({
      access_token: 'jwt-new',
      token_type: 'Bearer',
      expires_at: '2026-08-26T00:00:00Z',
      user: { user_id: 's1', username: 'xiaoming', user_type: 'STUDENT' },
    })
    getMeMock.mockResolvedValue(profile)
    logoutMock.mockResolvedValue(undefined)
    renderAuth()
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('anon'))

    fireEvent.click(screen.getByRole('button', { name: 'login' }))
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('user:小明'))
    expect(screen.getByTestId('token').textContent).toBe('jwt-new')

    fireEvent.click(screen.getByRole('button', { name: 'logout' }))
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('anon'))
    expect(screen.getByTestId('token').textContent).toBe('none')
    expect(logoutMock).toHaveBeenCalled()
  })
})
