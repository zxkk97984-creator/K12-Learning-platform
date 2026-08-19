import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './http'
import { ApiMemoryService } from './api-memory-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const memory = {
  memory_id: 'memory-1',
  memory_type: 'PREFERENCE',
  content: '我喜欢通过例子学习',
  tags: ['例子优先'],
  confidence: 'MEDIUM',
  status: 'ACTIVE',
  evidence_ids: ['evidence-1'],
  origin_candidate_id: null,
  user_confirmed: false,
  created_at: '2026-08-19T08:00:00Z',
  updated_at: '2026-08-19T08:00:00Z',
  confirmed_at: null,
}

describe('ApiMemoryService', () => {
  let service: ApiMemoryService

  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: { getItem: () => 'token-1' } })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiMemoryService()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('读取真实记忆并带 status/memory_type 筛选', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: [memory] }),
    )

    await expect(
      service.getMemories({ status: 'REMOVED', memory_type: 'PREFERENCE' }),
    ).resolves.toEqual([{ ...memory, student_id: '' }])
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/me/memories?status=REMOVED&memory_type=PREFERENCE',
    )
  })

  it('把四动作映射为 PATCH 请求，并读取版本化后的记忆', async () => {
    const edited = { ...memory, memory_id: 'memory-2', content: '我喜欢先看生活例子', user_confirmed: true }
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, { data: edited }),
    )

    await expect(service.updateMemory('memory-1', 'EDIT', edited.content)).resolves.toMatchObject({
      memory_id: 'memory-2',
      content: edited.content,
      user_confirmed: true,
    })
    expect(fetchMock.mock.calls[0]).toEqual([
      '/api/v1/me/memories/memory-1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ action: 'EDIT', content: edited.content }),
      }),
    ])

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { data: memory }))
    await service.updateMemory('memory-1', 'CONFIRM')
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ action: 'CONFIRM' }),
      }),
    )
  })

  it('读取证据详情，并将 401 转为 ApiError', async () => {
    const evidence = {
      evidence_id: 'evidence-1',
      source_type: 'CONVERSATION',
      event_ids: ['event-1'],
      payload: { dialogue_count: 3 },
      count: 1,
      first_occurred_at: '2026-08-18T00:00:00Z',
      last_occurred_at: '2026-08-18T00:00:00Z',
      derived_at: '2026-08-19T08:00:00Z',
      rule_version: 'memory-v1',
    }
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { data: evidence }))
    await expect(service.getEvidence('evidence-1')).resolves.toEqual({
      ...evidence,
      student_id: '',
    })

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: 'missing bearer token' } }),
    )
    await expect(service.getMemories()).rejects.toMatchObject(
      new ApiError(401, 'UNAUTHENTICATED', 'missing bearer token'),
    )
  })
})
