import { useEffect } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { Companion } from '@/features/companion'
import { ToastHost } from '@/features/feedback'

const NAV_ITEMS = [
  { to: '/home', label: '首页' },
  { to: '/library', label: '学习' },
  { to: '/quizzes', label: '测验' },
  { to: '/profile', label: '成长' },
  { to: '/settings', label: '设置' },
] as const

export function AppLayout() {
  const { currentUser, authUser, logout } = useAuth()
  const navigate = useNavigate()
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
      <header className="sticky top-0 z-20 border-b border-border bg-bg/90 backdrop-blur">
        <div className="mx-auto flex min-h-[68px] max-w-[var(--content)] items-center gap-7 px-gutter">
          <NavLink to="/home" className="font-display text-lg leading-none">
            霜铃
          </NavLink>
          <nav className="flex flex-1 items-center gap-1.5" aria-label="主导航">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'min-h-[44px] rounded-[10px] px-3.5 py-2.5 text-sm transition-colors',
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
                    'min-h-[44px] rounded-[10px] px-3.5 py-2.5 text-sm transition-colors',
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
                <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-fg font-display text-sm text-surface">
                  {(currentUser?.nickname ?? authUser?.username ?? '管').slice(0, 1)}
                </span>
                <span className="text-sm text-fg">
                  {currentUser?.nickname ?? (isAdmin ? '管理员' : authUser?.username)}
                </span>
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
      <main className="mx-auto max-w-[var(--content)] px-gutter">
        <Outlet />
      </main>
      <Companion />
      <ToastHost />
    </div>
  )
}
