import type {
  Book,
  BookProgress,
  Chapter,
  ChapterDetail,
  KnowledgePoint,
} from '@/entities/book/types'
import type { Stage } from '@/entities/student/types'
import type { CursorMeta } from './http'

export interface ContentListParams {
  stage?: Stage
  topic?: string
  search?: string
}

export interface BookPageParams extends ContentListParams {
  cursor?: string
  limit?: number
}

export interface BookPage {
  items: Book[]
  meta: CursorMeta
}

export interface ContentService {
  getBooks(params?: ContentListParams): Promise<Book[]>
  getBooksPage(params?: BookPageParams): Promise<BookPage>
  getBook(bookId: string): Promise<Book>
  getChapters(bookId: string): Promise<Chapter[]>
  getChapter(chapterId: string): Promise<ChapterDetail>
  getKnowledgePoint(knowledgePointId: string): Promise<KnowledgePoint>
  getProgress(): Promise<BookProgress[]>
  getBookProgress(bookId: string): Promise<BookProgress | null>
}
