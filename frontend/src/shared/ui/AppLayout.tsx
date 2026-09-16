import { useEffect } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { Companion, useTeacherName } from '@/features/companion'
import { ToastHost } from '@/features/feedback'
import { ScreenContextRouteSync } from '@/features/screen-context'
import { UserAvatar } from './UserAvatar'
import { BottomNav } from './BottomNav'

const NAV_ITEMS = [
  { to: '/home', label: '首页' },
  { to: '/library', label: '学习' },
  { to: '/quizzes', label: '练习' },
  // CodeLab：在线编程。仅加入桌面导航；移动端底部导航保持四项
  // （T17 验收与 mobile-learning/account-switch 的 E2E 明确断言四项）。
  { to: '/codelab', label: '编程' },
  { to: '/profile', label: '成长' },
] as const

export function AppLayout() {
  const { currentUser, authUser, logout } = useAuth()
  const navigate = useNavigate()
  const teacherName = useTeacherName()
  const isAdmin = authUser?.user_type === 'ADMIN'

  // 学段适配恢复（对齐原型 localStorage['shuangling-age']；1-B html[data-age]）
  useEffect(() => {
    const saved = window.localStorage.getItem('shuangling-age')
    if (saved === 'primary' || saved === 'senior') {
      document.documentElement.dataset.age = saved
    }
  }, [])

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-bg font-body text-fg">
      <ScreenContextRouteSync />
      <header className="sticky top-0 z-20 border-b border-border bg-bg/90 backdrop-blur">
        <div className="mx-auto flex min-h-[68px] max-w-[var(--content)] items-center gap-7 px-gutter">
          <NavLink to="/home" className="font-display text-lg leading-none">
            {teacherName}
          </NavLink>
          <nav
            className="hidden flex-1 items-center gap-1.5 md:flex"
            aria-label="主导航"
          >
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'min-h-[44px] rounded-[10px] px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'border border-border bg-surface text-fg shadow-sm'
                      : 'text-muted hover:bg-fg-soft hover:text-fg',
                  ].join(' ')
                }
              >
                {item.label}
              </NavLink>
            ))}
            {isAdmin ? (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  [
                    'min-h-[44px] rounded-[10px] px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'border border-border bg-surface text-fg shadow-sm'
                      : 'text-muted hover:bg-fg-soft hover:text-fg',
                  ].join(' ')
                }
              >
                管理
              </NavLink>
            ) : null}
          </nav>
          <div className="flex items-center gap-2.5">
            {currentUser || authUser ? (
              <>
                <UserAvatar
                  nickname={currentUser?.nickname ?? authUser?.username}
                  avatarUrl={currentUser?.avatar_url}
                  size="sm"
                />
                <span className="hidden text-sm text-fg md:inline">
                  {currentUser?.nickname ?? (isAdmin ? '管理员' : authUser?.username)}
                </span>
                <Link
                  to="/settings"
                  aria-label="设置"
                  className="grid h-10 w-10 place-items-center rounded-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                >
                  ⚙
                </Link>
                <button
                  type="button"
                  aria-label="退出登录"
                  className="rounded-[10px] px-2.5 py-1.5 text-xs text-muted hover:bg-fg-soft hover:text-fg"
                  onClick={() => void handleLogout()}
                >
                  退出
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className="rounded-[10px] border border-border bg-surface px-3 py-1.5 text-xs text-fg hover:border-fg"
              >
                登录
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[var(--content)] px-gutter pb-20 md:pb-10">
        <Outlet />
      </main>
      <BottomNav />
      <Companion />
      <ToastHost />
    </div>
  )
}
