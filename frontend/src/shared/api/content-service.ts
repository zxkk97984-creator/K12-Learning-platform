import type {
  Book,
  BookProgress,
  Chapter,
  ChapterDetail,
  KnowledgePoint,
} from '@/entities/book/types'
import type { Stage } from '@/entities/student/types'

export interface ContentListParams {
  stage?: Stage
  topic?: string
  search?: string
}

export interface ContentService {
  getBooks(params?: ContentListParams): Promise<Book[]>
  getBook(bookId: string): Promise<Book>
  getChapters(bookId: string): Promise<Chapter[]>
  getChapter(chapterId: string): Promise<ChapterDetail>
  getKnowledgePoint(knowledgePointId: string): Promise<KnowledgePoint>
  getProgress(): Promise<BookProgress[]>
  getBookProgress(bookId: string): Promise<BookProgress | null>
}
