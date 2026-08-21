import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiRecommendationService } from './api-recommendation'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('ApiRecommendationService', () => {
  let service: ApiRecommendationService

  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => 'token-1' } })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiRecommendationService()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('读取学生推荐列表', async () => {
    const recommendation = {
      recommendation_id: 'recommendation-1',
      student_id: 'student-1',
      recommendation_type: 'CONTINUE_READING',
      title: '继续阅读',
      description: '从上次位置继续。',
      reason: '最近有阅读记录。',
      evidence_ids: ['progress-1'],
      related_book_id: 'book-1',
      status: 'ACTIVE',
      created_at: '2026-08-21T10:00:00Z',
      updated_at: '2026-08-21T10:00:00Z',
    }
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: [recommendation] }),
    )

    await expect(service.getRecommendations()).resolves.toEqual([recommendation])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/me/recommendations')
  })

  it('dismiss 使用推荐资源路径', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: { recommendation_id: 'recommendation-1', status: 'DISMISSED' } }),
    )

    await service.dismissRecommendation('recommendation-1')

    expect(fetchMock.mock.calls[0]).toEqual([
      '/api/v1/me/recommendations/recommendation-1/dismiss',
      expect.objectContaining({ method: 'POST' }),
    ])
  })
})
