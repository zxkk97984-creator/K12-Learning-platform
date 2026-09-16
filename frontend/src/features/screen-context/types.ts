// Screen Context（架构 §8；纯前端 Context，不落服务器）

export interface ScreenContext {
  route: string
  pageType: string
  bookId?: string
  chapterId?: string
  chapterTitle?: string
  /** 0-D §14.2：当前可见内容块（可选） */
  contentBlockId?: string
  visibleSection?: string
  selectedText?: string
  knowledgePoints?: string[]
  actions?: string[]
  /** §4.3 正在讲解的测验/题目（错题讲解上下文）。 */
  quizSessionId?: string
  questionId?: string
}

/** 由路由推导页面类型；路由切换清理上下文时使用。 */
export function derivePageType(pathname: string): string {
  if (pathname.startsWith('/learn/')) return 'chapter_reader'
  if (pathname.startsWith('/books/')) return 'book_detail'
  if (pathname === '/library') return 'library'
  if (pathname === '/quizzes' || pathname.startsWith('/quizzes/')) return 'quiz_history'
  if (pathname.startsWith('/profile')) return 'profile'
  if (pathname === '/settings') return 'settings'
  return 'home'
}
