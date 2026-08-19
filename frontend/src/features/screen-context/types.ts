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
}
