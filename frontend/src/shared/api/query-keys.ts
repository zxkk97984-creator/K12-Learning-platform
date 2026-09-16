/** T07 查询键：用户数据 key 必须包含 user_id，防止跨账号缓存串用。 */

export const queryKeys = {
  me: () => ['me'] as const,
  progress: (userId: string) => ['progress', userId] as const,
  bookProgress: (userId: string, bookId: string) => ['book-progress', userId, bookId] as const,
  books: (userId: string, filters: Record<string, unknown>) =>
    ['books', userId, filters] as const,
  recommendations: (userId: string) => ['recommendations', userId] as const,
  quizSessions: (userId: string, filters: Record<string, unknown>) =>
    ['quiz-sessions', userId, filters] as const,
  conversations: (userId: string, status?: string) => ['conversations', userId, status] as const,
  memories: (userId: string) => ['memories', userId] as const,
}

/** 生成稳定的用户数据查询键；未提供 userId 时回退为空段（调用方不得用于用户数据）。 */
export function userScopedKey(scope: string, userId: string | null, ...rest: unknown[]) {
  return [scope, userId ?? 'anon', ...rest] as const
}
