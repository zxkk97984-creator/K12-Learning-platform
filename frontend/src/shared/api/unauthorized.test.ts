// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { waitFor } from '@testing-library/react'
import { emitUnauthorized, UNAUTHORIZED_EVENT } from './http'
import { fetchSSE } from './sse'

function jsonResponse(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => body,
  } as Response
}

describe('global 401 handling（Phase 5-A）', () => {
  beforeEach(() => {
    window.localStorage.setItem('shuangling-access-token', 'expired-token')
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('apiRequest 收到 401 派发统一未授权事件', async () => {
    const { apiRequest } = await import('./http')
    const handler = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: 'token expired' } }),
    )

    await expect(apiRequest('/me')).rejects.toThrow()
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1))
    window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  })

  it('SSE 收到 401 同样派发统一未授权事件', async () => {
    const handler = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: 'token expired' } }),
    )

    await expect(
      fetchSSE('/conversations/c1/messages', {
        method: 'POST',
        body: JSON.stringify({ content: 'hi' }),
        headers: { 'Content-Type': 'application/json' },
        onEvent: () => undefined,
        onError: () => undefined,
      }),
    ).rejects.toThrow()

    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1))
    window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  })

  it('emitUnauthorized 工具函数与常量一致', () => {
    const handler = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    emitUnauthorized()
    expect(handler).toHaveBeenCalledOnce()
    window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  })
})

describe('adminService raw fetch 401（Phase 5-A 整改 5）', () => {
  beforeEach(() => {
    window.localStorage.setItem('shuangling-access-token', 'expired-admin')
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('requestWithKey 路径：401 触发全局事件并抛 ApiError', async () => {
    const handler = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    const { adminService } = await import('./admin-service')
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: 'token expired' } }),
    )

    await expect(adminService.createBook({ title: 'x', grade_min: 1, grade_max: 9 })).rejects.toThrow()
    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1))
    window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  })

  it('uploadKnowledgeResource 路径：401 触发全局事件并抛 ApiError', async () => {
    const handler = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    const { adminService } = await import('./admin-service')
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: 'token expired' } }),
    )
    const file = new File(['pdf'], 'doc.pdf', { type: 'application/pdf' })

    await expect(
      adminService.uploadKnowledgeResource({
        file,
        source_name: 's',
        source_url: 'https://x',
        license: 'CC',
        copyright_status: '原创',
      }),
    ).rejects.toThrow()

    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1))
    window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  })
})

describe('SSE Idempotency-Key（Phase 5-A 整改 4）', () => {
  beforeEach(() => {
    window.localStorage.setItem('shuangling-access-token', 'tok')
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('sendMessage 每次生成并携带 Idempotency-Key header', async () => {
    const { ApiConversationService } = await import('./api-conversation-service')
    const service = new ApiConversationService()
    // SSE 401 → 立即抛错，但请求已发出可断言 header
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(401, {}))

    await expect(
      service.sendMessage('c1', '你好', undefined, { onError: () => undefined }),
    ).rejects.toThrow()

    const init = vi.mocked(fetch).mock.calls[0]
    const headers = (init[1] as RequestInit).headers as Record<string, string>
    // Headers 规范化为小写键
    expect(headers['idempotency-key']).toBeTruthy()
    expect(headers['content-type']).toBe('application/json')
    // 每次调用生成不同 key
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(401, {}))
    await expect(
      service.sendMessage('c1', '第二次', undefined, { onError: () => undefined }),
    ).rejects.toThrow()
    const second = vi.mocked(fetch).mock.calls[1]
    const h2 = (second[1] as RequestInit).headers as Record<string, string>
    expect(h2['idempotency-key']).not.toBe(headers['idempotency-key'])
  })
})
