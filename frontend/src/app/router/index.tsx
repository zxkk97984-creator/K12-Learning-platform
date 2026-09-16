import type { ReactNode } from 'react'
import { lazy, Suspense } from 'react'
import { createBrowserRouter, Link, Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { AppLayout } from '@/shared/ui/AppLayout'
import LoginPage from '@/pages/login/LoginPage'

// T25b：按测量把页面级组件拆成独立 chunk（路由级 code-split）。AppLayout/Login 保持即时
// 预加载与登录恢复，其余页面懒加载。Admin 独立成包，避免拖大学生主 bundle。
const HomePage = lazy(() => import('@/pages/home/HomePage'))
const LibraryPage = lazy(() => import('@/pages/library/LibraryPage'))
const BookDetailPage = lazy(() => import('@/pages/book/BookDetailPage'))
const ReaderPage = lazy(() => import('@/pages/reader/ReaderPage'))
const QuizzesPage = lazy(() => import('@/pages/quizzes/QuizzesPage'))
const QuizDetailPage = lazy(() => import('@/pages/quizzes/QuizDetailPage'))
const ProfilePage = lazy(() => import('@/pages/profile/ProfilePage'))
const MemoriesPage = lazy(() => import('@/pages/profile/MemoriesPage'))
const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'))
const AdminLayout = lazy(() => import('@/pages/admin').then((m) => ({ default: m.AdminLayout })))
const AdminDashboard = lazy(() => import('@/pages/admin').then((m) => ({ default: m.AdminDashboard })))
const AdminBooks = lazy(() => import('@/pages/admin').then((m) => ({ default: m.AdminBooks })))
const AdminKnowledge = lazy(() => import('@/pages/admin').then((m) => ({ default: m.AdminKnowledge })))
const AdminStyles = lazy(() => import('@/pages/admin').then((m) => ({ default: m.AdminStyles })))
const AdminChapters = lazy(() => import('@/pages/admin').then((m) => ({ default: m.AdminChapters })))

const withSuspense = (node: ReactNode) => <Suspense fallback={null}>{node}</Suspense>

function NotFoundPage() {
  const location = useLocation()
  return (
    <section className="py-12">
      <h1 className="font-display text-3xl text-fg">页面不存在</h1>
      <p className="mt-3 max-w-[52ch] text-sm leading-relaxed text-muted">
        你访问的地址「{location.pathname}」不存在，可能已移动或输入有误。
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Link
          to="/home"
          className="rounded-[10px] bg-accent px-4 py-2 text-sm text-surface hover:bg-accent/85"
        >
          返回首页
        </Link>
        <Link
          to="/library"
          className="rounded-[10px] border border-border bg-surface px-4 py-2 text-sm text-fg hover:border-fg"
        >
          去书库
        </Link>
      </div>
    </section>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { currentUser, authUser, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-muted">
        正在恢复登录态…
      </div>
    )
  }
  if (!currentUser && !authUser) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }
  return <>{children}</>
}

function AdminGuard({ children }: { children: ReactNode }) {
  const { authUser } = useAuth()
  if (!authUser || authUser.user_type !== 'ADMIN') {
    return (
      <section className="py-10">
        <h1 className="font-display text-3xl text-fg">403 · 仅管理员可访问</h1>
      </section>
    )
  }
  return <>{children}</>
}

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/home" replace /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/home', element: withSuspense(<HomePage />) },
      { path: '/library', element: withSuspense(<LibraryPage />) },
      { path: '/books/:bookId', element: withSuspense(<BookDetailPage />) },
      { path: '/learn/:bookId/:chapterId', element: withSuspense(<ReaderPage />) },
      { path: '/quizzes', element: withSuspense(<QuizzesPage />) },
      { path: '/quizzes/:quizId', element: withSuspense(<QuizDetailPage />) },
      { path: '/profile', element: withSuspense(<ProfilePage />) },
      { path: '/profile/memories', element: withSuspense(<MemoriesPage />) },
      { path: '/settings', element: withSuspense(<SettingsPage />) },
      {
        path: '/admin',
        element: (
          <AdminGuard>{withSuspense(<AdminLayout />)}</AdminGuard>
        ),
        children: [
          { index: true, element: withSuspense(<AdminDashboard />) },
          { path: 'books', element: withSuspense(<AdminBooks />) },
          { path: 'knowledge', element: withSuspense(<AdminKnowledge />) },
          { path: 'styles', element: withSuspense(<AdminStyles />) },
          { path: 'chapters', element: withSuspense(<AdminChapters />) },
        ],
      },
    ],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '*', element: <NotFoundPage /> },
])
