import type {
  Book,
  BookProgress,
  Chapter,
  ChapterDetail,
  ContentBlock,
  KnowledgePoint,
} from '@/entities/book/types'

import type { ContentListParams, ContentService } from './content-service'
import { ApiError, apiRequest } from './http'

type ApiContentListParams = ContentListParams & {
  cursor?: string
  limit?: number
}

interface ApiBookDTO {
  book_id: string
  title: string
  cover_url: string | null
  description: string | null
  grade_min: number
  grade_max: number
  difficulty: Book['difficulty']
  estimated_minutes: number
  author: string | null
  source_ids: string[]
  license: string | null
  copyright_status: string | null
  tags: unknown[]
  status: Book['status']
  chapter_count: number
}

interface ApiChapterDTO {
  chapter_id: string
  book_id: string
  title: string
  chapter_order: number
  summary: string | null
  estimated_minutes: number | null
  status: Chapter['status']
  is_completed?: boolean
}

interface ApiContentBlockDTO {
  block_id: string
  chapter_id: string
  block_type: ContentBlock['block_type']
  content: Record<string, unknown>
  block_order: number
  section_key: string | null
  knowledge_point_ids: string[]
}

interface ApiKnowledgePointDTO {
  knowledge_point_id: string
  name: string
  slug: string
  description: string | null
  topic: string | null
  parent_id: string | null
  status: KnowledgePoint['status']
}

interface ApiChapterDetailDTO {
  chapter: ApiChapterDTO
  content_blocks: ApiContentBlockDTO[]
  knowledge_points: ApiKnowledgePointDTO[]
}

const STAGE_RANGE: Record<NonNullable<ContentListParams['stage']>, [number, number]> = {
  PRIMARY: [1, 6],
  JUNIOR: [7, 9],
  SENIOR: [10, 12],
}

/** 现有原型路由仍使用 b1/ch3；真实 API 主键为 UUID，暂保留这两个入口别名。 */
const LEGACY_BOOK_TITLES: Record<string, string> = {
  b1: 'AI 不是魔法',
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value)
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function mapBook(dto: ApiBookDTO): Book {
  const tags = stringArray(dto.tags)
  return {
    book_id: dto.book_id,
    title: dto.title,
    cover_url: dto.cover_url,
    description: dto.description,
    grade_min: dto.grade_min,
    grade_max: dto.grade_max,
    difficulty: dto.difficulty,
    estimated_minutes: dto.estimated_minutes,
    author: dto.author,
    tags,
    keywords: tags[1] ?? '',
    status: dto.status,
    chapter_count: dto.chapter_count,
    source_ids: stringArray(dto.source_ids),
    license: dto.license,
    copyright_status: dto.copyright_status,
  }
}

function mapChapter(dto: ApiChapterDTO): Chapter {
  return {
    chapter_id: dto.chapter_id,
    book_id: dto.book_id,
    title: dto.title,
    chapter_order: dto.chapter_order,
    summary: dto.summary,
    estimated_minutes: dto.estimated_minutes,
    status: dto.status,
    is_completed: dto.is_completed,
  }
}

function mapContentBlock(dto: ApiContentBlockDTO): ContentBlock {
  return {
    block_id: dto.block_id,
    chapter_id: dto.chapter_id,
    block_type: dto.block_type,
    content: dto.content,
    block_order: dto.block_order,
    section_key: dto.section_key,
    knowledge_point_ids: dto.knowledge_point_ids,
  }
}

function mapKnowledgePoint(dto: ApiKnowledgePointDTO): KnowledgePoint {
  return {
    knowledge_point_id: dto.knowledge_point_id,
    name: dto.name,
    slug: dto.slug,
    description: dto.description,
    topic: dto.topic,
    parent_id: dto.parent_id,
    status: dto.status,
  }
}

function queryOf(params?: ApiContentListParams): string {
  if (!params) return ''
  const query = new URLSearchParams()
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.stage) {
    const [gradeMin, gradeMax] = STAGE_RANGE[params.stage]
    query.set('grade_min', String(gradeMin))
    query.set('grade_max', String(gradeMax))
  }
  if (params.topic) query.set('tag', params.topic)
  // The current backend accepts/ignores this contract parameter; local filtering below
  // keeps the existing ContentService search behavior until server-side search lands.
  if (params.search) query.set('search', params.search)
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

function searchBooks(books: Book[], search: string | undefined): Book[] {
  const needle = search?.trim().toLowerCase()
  if (!needle) return books
  return books.filter((book) =>
    `${book.title} ${book.description ?? ''} ${book.keywords} ${book.tags.join(' ')}`
      .toLowerCase()
      .includes(needle),
  )
}

export class ApiContentService implements ContentService {
  async getBooks(params?: ApiContentListParams): Promise<Book[]> {
    const payload = await apiRequest<ApiBookDTO[] | { items: ApiBookDTO[] }>(
      `/books${queryOf(params)}`,
    )
    const items = Array.isArray(payload) ? payload : payload.items
    return searchBooks(items.map(mapBook), params?.search)
  }

  async getBook(bookId: string): Promise<Book> {
    const resolvedBookId = await this.resolveBookId(bookId)
    return mapBook(await apiRequest<ApiBookDTO>(`/books/${encodeURIComponent(resolvedBookId)}`))
  }

  async getChapters(bookId: string): Promise<Chapter[]> {
    const resolvedBookId = await this.resolveBookId(bookId)
    const chapters = await apiRequest<ApiChapterDTO[]>(
      `/books/${encodeURIComponent(resolvedBookId)}/chapters`,
    )
    return chapters.map(mapChapter)
  }

  async getChapter(chapterId: string): Promise<ChapterDetail> {
    const resolvedChapterId = await this.resolveChapterId(chapterId)
    const detail = await apiRequest<ApiChapterDetailDTO>(
      `/chapters/${encodeURIComponent(resolvedChapterId)}`,
    )
    return {
      ...mapChapter(detail.chapter),
      content_blocks: detail.content_blocks.map(mapContentBlock),
      knowledge_points: detail.knowledge_points.map(mapKnowledgePoint),
    }
  }

  async getKnowledgePoint(knowledgePointId: string): Promise<KnowledgePoint> {
    return mapKnowledgePoint(
      await apiRequest<ApiKnowledgePointDTO>(
        `/knowledge-points/${encodeURIComponent(knowledgePointId)}`,
      ),
    )
  }

  async getProgress(): Promise<BookProgress[]> {
    return apiRequest<BookProgress[]>('/me/progress')
  }

  async getBookProgress(bookId: string): Promise<BookProgress | null> {
    const resolvedBookId = await this.resolveBookId(bookId)
    try {
      return await apiRequest<BookProgress>(`/me/progress/${encodeURIComponent(resolvedBookId)}`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }

  private async resolveBookId(bookId: string): Promise<string> {
    if (isUuid(bookId)) return bookId
    const title = LEGACY_BOOK_TITLES[bookId]
    if (!title) return bookId
    const books = await this.getBooks({ limit: 100 })
    return books.find((book) => book.title === title)?.book_id ?? bookId
  }

  private async resolveChapterId(chapterId: string): Promise<string> {
    if (isUuid(chapterId)) return chapterId
    const match = /^ch(\d+)$/.exec(chapterId)
    if (!match) return chapterId
    const chapters = await this.getChapters('b1')
    return chapters.find((chapter) => chapter.chapter_order === Number(match[1]))?.chapter_id ?? chapterId
  }
}
