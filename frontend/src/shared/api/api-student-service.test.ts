import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiStudentService } from './api-student-service'
import { getToken } from './auth'
import { ApiError } from './http'

function createStorage() {
  const store = new Map<string, string>()
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  }
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('ApiStudentService', () => {
  let service: ApiStudentService

  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: createStorage() })
    vi.stubGlobal('fetch', vi.fn())
    service = new ApiStudentService()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('login 成功存 token 并返回 AuthDTO', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, {
        data: {
          access_token: 'jwt-1',
          token_type: 'Bearer',
          expires_at: '2026-08-26T00:00:00Z',
          user: { user_id: 'u1', username: 'xiaoming', user_type: 'STUDENT' },
        },
      }),
    )
    const dto = await service.login('xiaoming', 'demo123')
    expect(dto.access_token).toBe('jwt-1')
    expect(getToken()).toBe('jwt-1')
  })

  it('login 失败（401）抛 ApiError 且不存 token', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(401, {
        error: { code: 'INVALID_CREDENTIALS', message: 'invalid username or password', details: null },
      }),
    )
    await expect(service.login('xiaoming', 'bad')).rejects.toMatchObject({
      code: 'INVALID_CREDENTIALS',
    })
    expect(getToken()).toBeNull()
  })

  it('getMe 请求带 Authorization 头', async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(
      jsonResponse(200, {
        data: {
          student_id: 's1',
          nickname: '小明',
          avatar_url: null,
          grade: 8,
          stage: 'JUNIOR',
          birth_date: null,
          language: 'zh-CN',
          learning_goal: null,
          current_teacher_role_id: null,
          learning_days: 0,
          total_learning_minutes: 0,
          completed_books: 0,
          completed_chapters: 0,
          quiz_count: 0,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
        },
      }),
    )
    ;(window.localStorage as { setItem: (k: string, v: string) => void }).setItem(
      'shuangling-access-token',
      'jwt-x',
    )
    const me = await service.getMe()
    expect(me.grade).toBe(8)
    expect(me.stage).toBe('JUNIOR')
    const init = fetchMock.mock.calls[0][1]
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer jwt-x')
  })

  it('401 时抛 ApiError（code 透传）', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(401, {
        error: { code: 'UNAUTHENTICATED', message: 'missing bearer token', details: null },
      }),
    )
    const error = await service.getMe().catch((err: unknown) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })
  })
})
