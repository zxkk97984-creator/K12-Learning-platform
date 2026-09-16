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
    public requestId?: string,
    public retryAfterMs?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  headers?: Record<string, string>
  /** AbortSignal 支持：路由/账号切换后取消迟到请求（T07）。 */
  signal?: AbortSignal
}

/** 轻量 fetch 封装：自动带 Authorization、解析 0-D 信封、非 2xx 抛结构化 ApiError */
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  return (await requestRaw<T, Record<string, unknown>>(path, options)).data
}

/** 信封版：同时返回 data 与 meta，用于分页/游标等带元数据的接口。 */
export async function apiRequestEnvelope<T, M = Record<string, unknown>>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<ApiEnvelope<T, M>> {
  return requestRaw<T, M>(path, options)
}

export interface ApiEnvelope<T, M = Record<string, unknown>> {
  data: T
  meta: M
}

export interface CursorMeta {
  next_cursor: string | null
  has_more: boolean
  total?: number | null
}

async function requestRaw<T, M>(
  path: string,
  options: ApiRequestOptions,
): Promise<{ data: T; meta: M }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  Object.assign(headers, options.headers)

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  })

  const requestId = response.headers?.get?.('x-request-id') ?? undefined
  const retryAfterHeader = response.headers?.get?.('retry-after')
  const retryAfterMs = parseRetryAfter(retryAfterHeader)

  if (response.status === 401) {
    emitUnauthorized()
  }
  if (response.status === 204) {
    return { data: undefined as T, meta: {} as M }
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
      requestId,
      retryAfterMs,
    )
  }
  const body = payload as { data: T; meta?: M }
  return { data: body.data, meta: (body.meta ?? {}) as M }
}

/** Retry-After 头部（HTTP 日期或秒）转毫秒；无法解析返回 undefined。 */
function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined
  const seconds = Number(header)
  if (Number.isFinite(seconds)) return Math.max(0, seconds) * 1000
  const date = Date.parse(header)
  if (!Number.isNaN(date)) return Math.max(0, date - Date.now())
  return undefined
}
