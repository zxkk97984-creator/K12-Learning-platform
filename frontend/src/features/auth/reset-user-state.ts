import { queryClient } from '@/app/providers/query'
import { clearToken } from '@/shared/api/auth'
import { useConversationStore } from '@/features/conversation/store/conversation-store'

/**
 * T06 统一的用户状态重置入口：登出、401、账号切换都要走这里。
 *
 * 负责：清除 token、中止并发对话流并清空对话内存状态、清除用户查询缓存、
 * 清空屏幕上下文（经由 conversation store 的 reset 完成 store 级清理）。
 * 未在此处清理的全局键（旧版 active-conversation）由 store.reset 一并清理。
 */
export function resetUserState(): void {
  clearToken()
  useConversationStore.getState().reset()
  // 清除所有 query 缓存，避免 A 用户的 /me、/progress、/recommendation 等
  // 在 B 登录后瞬间回填（跨账号 UI 残留）。
  queryClient.clear()
}
