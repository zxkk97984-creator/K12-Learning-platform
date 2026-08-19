import { contentService } from '@/mocks/services'

interface QuizSource {
  bookTitle: string
  chapterTitle: string
}

const sourceCache = new Map<string, QuizSource>()

/** 解析 quiz 来源书/章标题（只读 Mock 查询；失败降级占位） */
export async function quizSource(bookId: string | null, chapterId: string | null): Promise<QuizSource> {
  const key = `${bookId ?? ''}:${chapterId ?? ''}`
  const cached = sourceCache.get(key)
  if (cached) return cached
  let bookTitle = '—'
  let chapterTitle = '—'
  if (bookId) {
    try {
      bookTitle = (await contentService.getBook(bookId)).title
    } catch {
      bookTitle = '—'
    }
  }
  if (chapterId) {
    try {
      chapterTitle = (await contentService.getChapter(chapterId)).title
    } catch {
      try {
        const chapters = bookId ? await contentService.getChapters(bookId) : []
        chapterTitle = chapters.find((chapter) => chapter.chapter_id === chapterId)?.title ?? '—'
      } catch {
        chapterTitle = '—'
      }
    }
  }
  const result: QuizSource = { bookTitle, chapterTitle }
  sourceCache.set(key, result)
  return result
}
