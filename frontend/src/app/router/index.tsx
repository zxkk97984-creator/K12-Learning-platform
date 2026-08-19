import { createBrowserRouter, Navigate } from 'react-router-dom'

import HomePage from '@/pages/home/HomePage'
import LibraryPage from '@/pages/library/LibraryPage'
import BookDetailPage from '@/pages/book/BookDetailPage'
import ReaderPage from '@/pages/reader/ReaderPage'
import QuizzesPage from '@/pages/quizzes/QuizzesPage'
import QuizDetailPage from '@/pages/quizzes/QuizDetailPage'
import ProfilePage from '@/pages/profile/ProfilePage'
import MemoriesPage from '@/pages/profile/MemoriesPage'
import SettingsPage from '@/pages/settings/SettingsPage'
import { AppLayout } from '@/shared/ui/AppLayout'

function NotFoundPage() {
  return (
    <section className="py-10">
      <h1 className="font-display text-4xl text-fg">页面不存在</h1>
      <p className="mt-2 text-sm text-muted">404 · Phase 1 骨架占位</p>
    </section>
  )
}

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/home" replace /> },
  {
    element: <AppLayout />,
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
  { path: '*', element: <NotFoundPage /> },
])
