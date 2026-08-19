// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { adminService } from './admin-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('adminService', () => {
  beforeEach(() => {
    window.localStorage.setItem('shuangling-access-token', 'token-1')
    vi.stubGlobal('crypto', { randomUUID: () => 'request-1' })
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('读取 stats', async () => {
    const stats = {
      books_total: 1,
      books_published: 1,
      chapters_total: 2,
      knowledge_points_total: 3,
      resources_total: 4,
      resources_ready: 3,
      resources_failed: 1,
      students_total: 5,
    }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, { data: stats }))

    await expect(adminService.getStats()).resolves.toEqual(stats)
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/admin/stats')
  })

  it('创建书籍带 Idempotency-Key', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(201, {
        data: {
          book_id: 'book-1',
          title: '新书',
          status: 'DRAFT',
          grade_min: 7,
          grade_max: 9,
          tags: [],
          created_by: null,
          created_at: '2026-08-19T00:00:00Z',
        },
      }),
    )

    await adminService.createBook({ title: '新书', grade_min: 7, grade_max: 9 })

    const [, init] = vi.mocked(fetch).mock.calls[0]
    expect(init).toEqual(
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer token-1',
          'Idempotency-Key': 'request-1',
        }),
      }),
    )
  })

  it('上传资源构造 FormData 并带幂等头', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(201, {
        data: {
          resource_id: 'resource-1',
          source_name: '测试',
          source_url: 'https://x',
          author: null,
          license: 'CC-BY-4.0',
          copyright_status: '测试',
          storage_key: 'k',
          file_type: 'MARKDOWN',
          status: 'READY',
          error: null,
          created_at: '2026-08-19T00:00:00Z',
        },
      }),
    )

    await adminService.uploadKnowledgeResource({
      file: new File(['# x'], 'x.md', { type: 'text/markdown' }),
      source_name: '测试',
      source_url: 'https://x',
      license: 'CC-BY-4.0',
      copyright_status: '测试',
    })

    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('/api/v1/admin/knowledge/resources')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toBe('request-1')
    const body = init?.body as FormData
    expect(body.get('source_name')).toBe('测试')
    expect((body.get('file') as File).name).toBe('x.md')
  })
})
