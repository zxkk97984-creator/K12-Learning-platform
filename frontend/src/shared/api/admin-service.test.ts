// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { adminService } from './admin-service'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => body,
  } as Response
}

describe('adminService 合并完整性（Phase 5-A 整改回归）', () => {
  beforeEach(() => {
    window.localStorage.setItem('shuangling-access-token', 'tok')
    vi.stubGlobal('crypto', { randomUUID: () => 'fixed-key' })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('扩展方法真实存在于运行时对象上（getAdminMe/createChapter 等）', () => {
    for (const method of [
      'getAdminMe',
      'getTeacherRoles',
      'createTeacherRole',
      'patchTeacherRole',
      'createChapter',
      'patchChapter',
      'createContentBlock',
      'createKnowledgePoint',
    ] as const) {
      expect(typeof (adminService as Record<string, unknown>)[method]).toBe('function')
    }
  })

  it('getAdminMe 携带 Bearer token 请求 /me/admin', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        data: { admin_id: 'a1', user_id: 'u1', display_name: 'd', role_level: 'SUPER' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await adminService.getAdminMe()
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/me/admin')
    expect((init as { headers: Record<string, string> }).headers.Authorization).toBe('Bearer tok')
  })
})
