import { getToken } from './auth'

/** 相对路径，由 vite proxy 转发到后端（默认 localhost:8000，可用 VITE_API_PROXY_TARGET 覆盖） */
export const API_BASE = '/api/v1'

/** 全局 401 事件：任何 API/SSE 收到 401 时派发，AuthProvider 监听后清除登录态 */
export const UNAUTHORIZED_EVENT = 'shuangling:unauthorized'

export function emitUnauthorized(): void {
  // 兼容非 DOM 测试环境（node 下可能存在不完整 window 全局）
  const target = typeof window !== 'undefined' ? window : undefined
  if (target && typeof target.dispatchEvent === 'function') {
    target.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }
}

/** 供测试注入：读取事件名常量，避免魔法串散落 */
export function isUnauthorizedStatus(status: number): boolean {
  return status === 401
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  headers?: Record<string, string>
}

/** 轻量 fetch 封装：自动带 Authorization、解析 0-D 信封、非 2xx 抛结构化 ApiError */
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  Object.assign(headers, options.headers)

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })

  if (response.status === 401) {
    emitUnauthorized()
  }
  if (response.status === 204) {
    return undefined as T
  }

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; details?: unknown } })
      ?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? `HTTP ${response.status}`,
      error?.details,
    )
  }
  return (payload as { data: T }).data
}
