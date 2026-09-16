import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearToken, getToken, setToken } from './auth'
import { ApiError, apiRequest } from './http'

function createStorage() {
  const store = new Map<string, string>()
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  }
}

describe('apiRequest（0-D 信封解析）', () => {
  beforeEach(() => {
    const storage = createStorage()
    vi.stubGlobal('window', { localStorage: storage })
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('成功响应解析 { data } 并解包', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: { pong: true }, meta: {} }),
    } as unknown as Response)
    await expect(apiRequest<{ pong: boolean }>('/ping')).resolves.toEqual({ pong: true })
  })

  it('非 2xx 抛结构化 ApiError（code/message/details）', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        error: { code: 'UNAUTHENTICATED', message: 'missing bearer token', details: null },
      }),
    } as Response)
    const error = await apiRequest('/me').catch((err: unknown) => err)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })
  })

  it('带 token 时自动添加 Authorization 头', async () => {
    setToken('token-abc')
    const fetchMock = vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: null }),
    } as Response)
    await apiRequest('/me')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/me')
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-abc')
  })

  it('204 返回 undefined', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('no body')
      },
    } as unknown as Response)
    await expect(apiRequest<void>('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
  })

  it('错误时携带 requestId 与 retryAfterMs（来自响应头）', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 429,
      headers: { get: (key: string) => (key === 'x-request-id' ? 'req-123' : key === 'retry-after' ? '2' : null) },
      json: async () => ({ error: { code: 'TOO_MANY_REQUESTS', message: '慢点' } }),
    } as unknown as Response)
    const error = (await apiRequest('/me').catch((err: unknown) => err)) as ApiError
    expect(error.requestId).toBe('req-123')
    expect(error.retryAfterMs).toBe(2000)
  })

  it('转发 AbortSignal 至 fetch（路由/切换后可取消）', async () => {
    const controller = new AbortController()
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ data: null }),
    } as unknown as Response)
    await apiRequest('/me', { signal: controller.signal })
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('/api/v1/me')
    expect(init?.signal).toBe(controller.signal)
  })
})

describe('auth token 存取', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: createStorage() })
  })
  afterEach(() => {
    clearToken()
    vi.unstubAllGlobals()
  })

  it('setToken/getToken/clearToken 读写 localStorage', () => {
    setToken('abc')
    expect(getToken()).toBe('abc')
    clearToken()
    expect(getToken()).toBeNull()
  })
})
