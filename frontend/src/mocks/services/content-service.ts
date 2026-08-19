import type { ContentService, ContentListParams } from '@/shared/api/content-service'
import type { Book, ChapterDetail } from '@/entities/book/types'
import type { Stage } from '@/entities/student/types'

import { delay } from '../delay'
import {
  mockBookProgress,
  mockBooks,
  mockChapterDetails,
  mockChapters,
  mockKnowledgePoints,
} from '../data/books'

function stageOfBook(book: Book): Stage {
  if (book.grade_max <= 6) return 'PRIMARY'
  if (book.grade_min >= 10) return 'SENIOR'
  return 'JUNIOR'
}

export class MockContentService implements ContentService {
  async getBooks(params?: ContentListParams) {
    const stage = params?.stage
    const topic = params?.topic
    const search = params?.search?.trim().toLowerCase()
    let list = mockBooks
    if (stage) list = list.filter((book) => stageOfBook(book) === stage)
    if (topic) list = list.filter((book) => book.tags.includes(topic))
    if (search) {
      list = list.filter((book) =>
        `${book.title} ${book.keywords} ${book.tags.join(' ')}`.toLowerCase().includes(search),
      )
    }
    return delay(list, 200)
  }

  async getBook(bookId: string) {
    const book = mockBooks.find((item) => item.book_id === bookId)
    if (!book) throw new Error(`BOOK_NOT_FOUND: ${bookId}`)
    return delay(book, 200)
  }

  async getChapters(bookId: string) {
    return delay(mockChapters.filter((chapter) => chapter.book_id === bookId), 200)
  }

  async getChapter(chapterId: string) {
    const detail: ChapterDetail | undefined = mockChapterDetails[chapterId]
    if (!detail) throw new Error(`CHAPTER_NOT_FOUND: ${chapterId}`)
    return delay(detail, 200)
  }

  async getKnowledgePoint(knowledgePointId: string) {
    const point = mockKnowledgePoints.find((item) => item.knowledge_point_id === knowledgePointId)
    if (!point) throw new Error(`KNOWLEDGE_POINT_NOT_FOUND: ${knowledgePointId}`)
    return delay(point, 200)
  }

  async getProgress() {
    return delay(mockBookProgress.map((item) => ({ ...item })), 200)
  }

  async getBookProgress(bookId: string) {
    const progress = mockBookProgress.find((item) => item.book_id === bookId)
    return delay(progress ? { ...progress } : null, 200)
  }
}
