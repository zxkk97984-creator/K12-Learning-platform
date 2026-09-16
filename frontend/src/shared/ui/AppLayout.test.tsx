// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/companion', () => ({
  Companion: () => <span aria-hidden="true" />,
  useTeacherName: () => '霜铃',
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    currentUser: { nickname: '小明', grade: 8 },
    authUser: { user_type: 'STUDENT' },
    logout: vi.fn(),
  }),
}))

vi.mock('@/features/screen-context', () => ({ ScreenContextRouteSync: () => null }))
vi.mock('@/features/feedback', () => ({ ToastHost: () => null }))
vi.mock('./UserAvatar', () => ({ UserAvatar: () => <span data-testid="avatar" /> }))

import { AppLayout } from './AppLayout'

afterEach(cleanup)

function renderLayout() {
  const Probe = () => <div data-testid="probe">页面内容</div>
  return render(
    <MemoryRouter initialEntries={['/home']}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/home" element={<Probe />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppLayout（T17 §5.2 全局导航）', () => {
  it('桌面顶部导航含首页/学习/练习/成长，测验改名练习', () => {
    renderLayout()
    const topNav = screen.getByRole('navigation', { name: '主导航' })
    for (const label of ['首页', '学习', '练习', '成长']) {
      expect(topNav.textContent).toContain(label)
    }
    // "测验"已改名"练习"，不应再称作测验
    expect(topNav.textContent).not.toContain('测验')
  })

  it('提供设置入口（账户区）与退出', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: '设置' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '退出登录' })).toBeTruthy()
  })

  it('渲染底部四项导航（移动端）', () => {
    renderLayout()
    const bottomNav = screen.getByRole('navigation', { name: '底部主导航' })
    for (const label of ['首页', '学习', '练习', '成长']) {
      expect(bottomNav.textContent).toContain(label)
    }
  })

  it('非管理员学生不显示管理入口', () => {
    renderLayout()
    const topNav = screen.getByRole('navigation', { name: '主导航' })
    expect(topNav.textContent).not.toContain('管理')
  })

  it('渲染渲染的内容出口', () => {
    renderLayout()
    expect(screen.getByTestId('probe')).toBeTruthy()
  })
})
