import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiCodeLabService } from './api-codelab-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit]
  return { url, init }
}

describe('ApiCodeLabService', () => {
  let service: ApiCodeLabService
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.stubGlobal('window', {
      localStorage: { getItem: () => 'token-1' },
      dispatchEvent: () => true,
    })
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    service = new ApiCodeLabService()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('任务列表走 /codelab/tasks 并解包信封', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        data: [
          {
            task_id: 't1',
            slug: 'demo',
            title: '示例任务',
            description: '说明',
            has_tests: true,
            status: 'PUBLISHED',
          },
        ],
        meta: {},
      }),
    )
    const tasks = await service.listTasks()
    expect(tasks).toHaveLength(1)
    expect(tasks[0].slug).toBe('demo')
    expect(lastCall(fetchMock).url).toBe('/api/v1/codelab/tasks')
  })

  it('任务详情对 taskId 做 URL 编码', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { data: {}, meta: {} }))
    await service.getTask('a b/c')
    expect(lastCall(fetchMock).url).toBe('/api/v1/codelab/tasks/a%20b%2Fc')
  })

  it('运行代码 POST /codelab/runs，请求体为 {task_id, code}', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, { data: { run_id: 'r1', outputs: [] }, meta: {} }),
    )
    await service.runCode('t1', 'print(1)')
    const { url, init } = lastCall(fetchMock)
    expect(url).toBe('/api/v1/codelab/runs')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ task_id: 't1', code: 'print(1)' })
  })

  it('请求评审 POST /codelab/reviews，请求体为 {run_id}', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, { data: { review_id: 'v1' }, meta: {} }),
    )
    await service.requestReview('r1')
    const { url, init } = lastCall(fetchMock)
    expect(url).toBe('/api/v1/codelab/reviews')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ run_id: 'r1' })
  })

  it('读取评审 GET /codelab/reviews/{id}', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        data: {
          review_id: 'v1',
          run_id: 'r1',
          status: 'COMPLETED',
          grading_mode: 'tests',
          deterministic_available: true,
          correctness_status: 'PASSED',
          final_score_100: 88,
          functional_max: 60,
          robustness_max: 10,
          algorithm_max: 20,
          quality_max: 10,
        },
        meta: {},
      }),
    )
    const review = await service.getReview('v1')
    expect(lastCall(fetchMock).url).toBe('/api/v1/codelab/reviews/v1')
    expect(review.final_score_100).toBe(88)
  })

  it('后端返回错误信封时抛出带 code 的 ApiError', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(503, {
        error: { code: 'CODELAB_DISABLED', message: 'CodeLab 未启用' },
      }),
    )
    await expect(service.listTasks()).rejects.toMatchObject({
      status: 503,
      code: 'CODELAB_DISABLED',
    })
  })
})
