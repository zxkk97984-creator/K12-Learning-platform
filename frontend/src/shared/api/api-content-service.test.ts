import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiContentService } from './api-content-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const bookDto = {
  book_id: 'book-1',
  title: 'AI 不是魔法',
  cover_url: null,
  description: '从推荐系统、训练数据到算法公平。',
  grade_min: 7,
  grade_max: 9,
  difficulty: 'MEDIUM',
  estimated_minutes: 90,
  author: null,
  source_ids: [],
  license: null,
  copyright_status: null,
  tags: ['AI 基础', '训练数据 · 标签 · 算法'],
  status: 'PUBLISHED',
  published_at: null,
  chapter_count: 5,
}

describe('ApiContentService', () => {
  let service: ApiContentService

  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => null } })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiContentService()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getBooks 请求后端分页筛选参数，并从 tags 派生 keywords 与真实章数', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: [bookDto], meta: { next_cursor: null, has_more: false } }),
    )

    const books = await service.getBooks({
      stage: 'JUNIOR',
      topic: 'AI 基础',
      search: '训练',
      cursor: 'cursor-1',
      limit: 12,
    })

    expect(books[0]).toMatchObject({
      book_id: 'book-1',
      keywords: '训练数据 · 标签 · 算法',
      chapter_count: 5,
    })
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/books?cursor=cursor-1&limit=12&grade_min=7&grade_max=9&tag=AI+%E5%9F%BA%E7%A1%80&search=%E8%AE%AD%E7%BB%83',
    )
  })

  it('getBook 与 getChapters 返回实体类型，并保留后端 snake_case 字段', async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(200, { data: bookDto }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          data: [
            {
              chapter_id: 'chapter-3',
              book_id: 'book-1',
              title: '训练数据',
              chapter_order: 3,
              summary: null,
              estimated_minutes: 13,
              status: 'PUBLISHED',
            },
          ],
        }),
      )

    await expect(service.getBook('book-1')).resolves.toMatchObject({ book_id: 'book-1', chapter_count: 5 })
    await expect(service.getChapters('book-1')).resolves.toEqual([
      expect.objectContaining({ chapter_id: 'chapter-3', chapter_order: 3 }),
    ])
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/books/book-1',
      '/api/v1/books/book-1/chapters',
    ])
  })

  it('getChapter 扁平化后端嵌套 chapter，并返回内容块与知识点', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, {
        data: {
          chapter: {
            chapter_id: 'chapter-3',
            book_id: 'book-1',
            title: '训练数据',
            chapter_order: 3,
            summary: null,
            estimated_minutes: 13,
            status: 'PUBLISHED',
          },
          content_blocks: [
            {
              block_id: 'block-1',
              chapter_id: 'chapter-3',
              block_type: 'PARAGRAPH',
              content: { text: '真实内容' },
              block_order: 1,
              section_key: '训练数据 · 导入',
              knowledge_point_ids: [],
            },
          ],
          knowledge_points: [
            {
              knowledge_point_id: 'kp-1',
              name: '训练数据',
              slug: 'training_data',
              description: null,
              topic: 'AI 基础',
              parent_id: null,
              status: 'ACTIVE',
            },
          ],
        },
      }),
    )

    await expect(service.getChapter('chapter-3')).resolves.toMatchObject({
      chapter_id: 'chapter-3',
      title: '训练数据',
      content_blocks: [expect.objectContaining({ content: { text: '真实内容' } })],
      knowledge_points: [expect.objectContaining({ slug: 'training_data' })],
    })
  })

  it('getKnowledgePoint 透传知识点实体', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, {
        data: {
          knowledge_point_id: 'kp-1',
          name: '训练数据',
          slug: 'training_data',
          description: '用于帮助机器发现规律的例子。',
          topic: 'AI 基础',
          parent_id: null,
          status: 'ACTIVE',
        },
      }),
    )

    await expect(service.getKnowledgePoint('kp-1')).resolves.toMatchObject({
      knowledge_point_id: 'kp-1',
      slug: 'training_data',
    })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/knowledge-points/kp-1')
  })

  it('3-E 之前进度方法默认降级，不调用 Learning API', async () => {
    const fetchMock = vi.mocked(fetch)

    await expect(service.getProgress()).resolves.toEqual([])
    await expect(service.getBookProgress('book-1')).resolves.toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
