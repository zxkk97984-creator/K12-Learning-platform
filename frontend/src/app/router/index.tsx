import type { ReactNode } from 'react'
import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import HomePage from '@/pages/home/HomePage'
import LibraryPage from '@/pages/library/LibraryPage'
import BookDetailPage from '@/pages/book/BookDetailPage'
import ReaderPage from '@/pages/reader/ReaderPage'
import QuizzesPage from '@/pages/quizzes/QuizzesPage'
import QuizDetailPage from '@/pages/quizzes/QuizDetailPage'
import ProfilePage from '@/pages/profile/ProfilePage'
import MemoriesPage from '@/pages/profile/MemoriesPage'
import SettingsPage from '@/pages/settings/SettingsPage'
import LoginPage from '@/pages/login/LoginPage'
import { AppLayout } from '@/shared/ui/AppLayout'

function NotFoundPage() {
  return (
    <section className="py-10">
      <h1 className="font-display text-4xl text-fg">页面不存在</h1>
      <p className="mt-2 text-sm text-muted">404 · Phase 1 骨架占位</p>
    </section>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { currentUser, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-muted">
        正在恢复登录态…
      </div>
    )
  }
  if (!currentUser) {
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

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/home" replace /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: '/home', element: <HomePage /> },
      { path: '/library', element: <LibraryPage /> },
      { path: '/books/:bookId', element: <BookDetailPage /> },
      { path: '/learn/:bookId/:chapterId', element: <ReaderPage /> },
      { path: '/quizzes', element: <QuizzesPage /> },
      { path: '/quizzes/:quizId', element: <QuizDetailPage /> },
      { path: '/profile', element: <ProfilePage /> },
      { path: '/profile/memories', element: <MemoriesPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '*', element: <NotFoundPage /> },
])
