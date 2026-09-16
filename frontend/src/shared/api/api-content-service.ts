import type {
  Book,
  BookProgress,
  Chapter,
  ChapterDetail,
  ContentBlock,
  KnowledgePoint,
} from '@/entities/book/types'

import type { BookPage, ContentListParams, ContentService } from './content-service'
import { ApiError, apiRequest, apiRequestEnvelope } from './http'
import type { CursorMeta } from './http'

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
  if (params.search) query.set('search', params.search)
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

export class ApiContentService implements ContentService {
  async getBooksPage(params?: ApiContentListParams): Promise<BookPage> {
    // T04/T05：信封解析；后端全库搜索+分页，服务端返回 meta(游标/总数)。
    const { data: items, meta } = await apiRequestEnvelope<ApiBookDTO[] | { items: ApiBookDTO[] }, CursorMeta>(
      `/books${queryOf(params)}`,
    )
    const list = Array.isArray(items) ? items : items.items
    return { items: list.map(mapBook), meta }
  }

  async getBooks(params?: ApiContentListParams): Promise<Book[]> {
    // 兼容接口：仅返回第一页。书库发现请使用 getBooksPage（支持分页/总数）。
    const page = await this.getBooksPage(params)
    return page.items
  }

  async getBook(bookId: string): Promise<Book> {
    // Phase 5-B-I：仅接受真实 UUID，不再做 b1 等旧原型别名换算
    return mapBook(await apiRequest<ApiBookDTO>(`/books/${encodeURIComponent(bookId)}`))
  }

  async getChapters(bookId: string): Promise<Chapter[]> {
    return apiRequest<ApiChapterDTO[]>(`/books/${encodeURIComponent(bookId)}/chapters`).then(
      (chapters) => chapters.map(mapChapter),
    )
  }

  async getChapter(chapterId: string): Promise<ChapterDetail> {
    const detail = await apiRequest<ApiChapterDetailDTO>(
      `/chapters/${encodeURIComponent(chapterId)}`,
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
    try {
      return await apiRequest<BookProgress>(`/me/progress/${encodeURIComponent(bookId)}`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }


}
