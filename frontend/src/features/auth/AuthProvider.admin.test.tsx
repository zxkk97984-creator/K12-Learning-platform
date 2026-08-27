// @vitest-environment jsdom
import { screen, act, cleanup, render, waitFor  } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  getMe: vi.fn(),
  getAdminMe: vi.fn(),
}))

vi.mock('@/shared/services', () => ({
  studentService: {
    login: mocks.login,
    logout: mocks.logout,
    getMe: mocks.getMe,
  },
}))
vi.mock('@/shared/api/admin-service', () => ({
  adminService: { getAdminMe: mocks.getAdminMe },
}))

import { AuthProvider, useAuth } from './AuthProvider'

const ADMIN_TOKEN =
  'eyJhbGciOiJIUzI1NiJ9.' +
  btoa(JSON.stringify({ sub: 'u-admin', user_type: 'ADMIN' })).replace(/=/g, '') +
  '.sig'

const adminAuth = {
  access_token: ADMIN_TOKEN,
  token_type: 'Bearer',
  expires_at: '2027-01-01T00:00:00Z',
  user: { user_id: 'u-admin', username: 'admin', user_type: 'ADMIN' },
}

function Probe() {
  const { authUser, currentUser } = useAuth()
  return (
    <output data-testid="state">
      {authUser?.user_type ?? 'none'}|{currentUser ? 'student-loaded' : 'no-student'}
    </output>
  )
}

describe('AuthProvider admin verification（Phase 5-A）', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    mocks.login.mockResolvedValue(adminAuth)
    mocks.logout.mockResolvedValue(undefined)
    mocks.getAdminMe.mockResolvedValue({ admin_id: 'a1', role_level: 'SUPER' })
    mocks.getMe.mockResolvedValue({
      student_id: 's', nickname: 'n', grade: 8, learning_days: 0,
      total_learning_minutes: 0, completed_books: 0, completed_chapters: 0, quiz_count: 0,
    })
    ;(window as unknown as { __auth?: unknown }).__auth = undefined
  })

  afterEach(() => {
    cleanup()
    window.localStorage.removeItem('shuangling-access-token')
  })

  it('ADMIN 登录成功必须通过真实 /me/admin 验证', async () => {
    let latest: ReturnType<typeof useAuth> | null = null
    render(
      <AuthProvider>
        <Hook onReady={(a) => (latest = a)} />
      </AuthProvider>,
    )
    await act(async () => {
      await latest!.login('admin', 'pw')
    })
    expect(mocks.getAdminMe).toHaveBeenCalled()
  })

  it('/me/admin 验证失败时清除登录态并不保留 token', async () => {
    mocks.getAdminMe.mockRejectedValue(new Error('403'))
    let latest: ReturnType<typeof useAuth> | null = null
    function Capture() {
      latest = useAuth()
      return null
    }
    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    )
    await expect(
      act(async () => {
        await latest!.login('admin', 'pw')
      }),
    ).rejects.toThrow()
    await waitFor(() => expect(latest!.token).toBeNull())
    expect(window.localStorage.getItem('shuangling-access-token')).toBeNull()
  })

  it('全局 401 事件触发清除登录态', async () => {
    let latest: ReturnType<typeof useAuth> | null = null
    function Capture() {
      latest = useAuth()
      return null
    }
    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    )
    await act(async () => {
      await latest!.login('admin', 'pw')
    })
    expect(latest!.token).not.toBeNull()

    act(() => {
      window.dispatchEvent(new CustomEvent('shuangling:unauthorized'))
    })
    await waitFor(() => expect(latest!.token).toBeNull())
  })
})

function Hook({ onReady }: { onReady: (a: ReturnType<typeof useAuth>) => void }) {
  const auth = useAuth()
  onReady(auth)
  return null
}

describe('AuthProvider 刷新恢复的 ADMIN 验证（Phase 5-A 整改 1）', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    mocks.logout.mockResolvedValue(undefined)
    mocks.getMe.mockResolvedValue({
      student_id: 's', nickname: 'n', grade: 8, learning_days: 0,
      total_learning_minutes: 0, completed_books: 0, completed_chapters: 0, quiz_count: 0,
    })
    // 模拟用户此前已登录 ADMIN：localStorage 预置 token
    window.localStorage.setItem('shuangling-access-token', ADMIN_TOKEN)
    mocks.login.mockResolvedValue(adminAuth)
    mocks.getAdminMe.mockResolvedValue({ admin_id: 'a1', role_level: 'SUPER' })
  })

  afterEach(() => {
    cleanup()
    window.localStorage.clear()
  })

  it('(a) 刷新时 ADMIN 必须触发 getAdminMe；成功保留 authUser 且不调学生 getMe', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(mocks.getAdminMe).toHaveBeenCalledTimes(1))
    await waitFor(() => {
      const state = screen.getByTestId('state').textContent
      expect(state).toContain('ADMIN')
      expect(state).toContain('no-student') // 未调用学生 getMe
    })
    // 学生接口从未被调用
    expect(mocks.getMe).not.toHaveBeenCalled()
    // 登录态保持
    expect(window.localStorage.getItem('shuangling-access-token')).toBe(ADMIN_TOKEN)
  })

  it('(b) 刷新时 getAdminMe reject → token/localStorage/authUser 全部清空且不调 getMe', async () => {
    mocks.getAdminMe.mockRejectedValue(new Error('403 ADMIN_PROFILE_REQUIRED'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(mocks.getAdminMe).toHaveBeenCalledTimes(1))
    await waitFor(() => {
      const state = screen.getByTestId('state').textContent
      expect(state).toBe('none|no-student')
    })
    expect(window.localStorage.getItem('shuangling-access-token')).toBeNull()
    expect(mocks.getMe).not.toHaveBeenCalled()
  })
})
