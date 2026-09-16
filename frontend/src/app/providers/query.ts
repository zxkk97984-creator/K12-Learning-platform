import { QueryClient } from '@tanstack/react-query'

import { ApiError, isUnauthorizedStatus } from '@/shared/api/http'

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504, 502])

/**
 * T07 查询重试策略：
 * - 401/403 不重试（权限失败，清用户状态由 AuthProvider 的 UNAUTHORIZED_EVENT 处理）；
 * - 网络异常 / 5xx 最多自动重试 1 次；
 * - 429 尊重 Retry-After（取 ApiError.retryAfterMs，未提供时用默认 1000ms）。
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false
  if (error instanceof ApiError) {
    if (isUnauthorizedStatus(error.status) || error.status === 403) return false
    if (error.status === 429) return true
    return RETRYABLE_STATUS.has(error.status)
  }
  // 网络/超时等 fetch 原生错误（非 ApiError）：可重试。
  return true
}

export function retryDelay(failureCount: number, error: unknown): number {
  if (error instanceof ApiError && error.status === 429 && error.retryAfterMs !== undefined) {
    return error.retryAfterMs
  }
  return Math.min(1000 * 2 ** failureCount, 8000)
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: shouldRetry,
      retryDelay,
    },
    mutations: {
      retry: 0,
    },
  },
})
