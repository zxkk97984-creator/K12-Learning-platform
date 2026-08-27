import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import type { AuthUser, StudentProfile } from '@/entities/student/types'
import { clearToken, getToken } from '@/shared/api/auth'
import { ApiError, UNAUTHORIZED_EVENT } from '@/shared/api/http'
import { adminService } from '@/shared/api/admin-service'
import { studentService } from '@/shared/services'

interface AuthContextValue {
  token: string | null
  authUser: AuthUser | null
  currentUser: StudentProfile | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
}

function decodeAuthUser(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(
      atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')),
    )
    return {
      user_id: String(payload.sub ?? ''),
      username: String(payload.username ?? ''),
      user_type: payload.user_type === 'ADMIN' ? 'ADMIN' : 'STUDENT',
    }
  } catch {
    return null
  }
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [currentUser, setCurrentUser] = useState<StudentProfile | null>(null)
  const [loading, setLoading] = useState(true)

  // Phase 5-A：ADMIN 必须通过真实后台接口验证（require_admin 严格校验
  // admins 行存在且 enabled），不能只依赖前端 JWT decode。
  const verifyAdmin = useCallback(async (): Promise<boolean> => {
    try {
      await adminService.getAdminMe()
      return true
    } catch {
      return false
    }
  }, [])

  // 刷新保持登录：恢复 token → 拉当前用户；401 清除（Phase 2 验收「刷新」）
  useEffect(() => {
    const stored = getToken()
    if (!stored) {
      setLoading(false)
      return
    }
    setTokenState(stored)
    const decoded = decodeAuthUser(stored)
    const restore = async () => {
      // Phase 5-A 整改：刷新恢复时 ADMIN 也必须通过真实 /me/admin 验证；
      // 不再提前 return 跳过验证。成功才保留 authUser；失败清除全部登录态。
      if (decoded?.user_type === 'ADMIN') {
        // 乐观设置 authUser，避免 RequireAuth 在异步验证完成前重定向到 /login；
        // 验证失败时 clearAuthState 统一清除。
        setAuthUser(decoded)
        const okAdmin = await verifyAdmin()
        if (!okAdmin) {
          clearAuthState()
          return
        }
        // ADMIN 不调用学生 getMe
        return
      }
      if (!decoded) {
        clearAuthState()
        return
      }
      try {
        setCurrentUser(await studentService.getMe())
      } catch (error: unknown) {
        if (error instanceof ApiError && error.status === 401) {
          clearAuthState()
        } else {
          throw error
        }
      }
      setAuthUser(decoded)
    }
    restore()
      .catch((error: unknown) => {
        console.error('auth restore failed', error)
        clearAuthState()
      })
      .finally(() => setLoading(false))
  }, [])

  const refreshMe = useCallback(async () => {
    const me = await studentService.getMe()
    setCurrentUser(me)
  }, [])

  const clearAuthState = useCallback(() => {
    clearToken()
    setTokenState(null)
    setAuthUser(null)
    setCurrentUser(null)
  }, [])

  const login = useCallback(
    async (username: string, password: string) => {
      const dto = await studentService.login(username, password)
      setTokenState(dto.access_token)
      setAuthUser(dto.user)
      if (dto.user.user_type === 'ADMIN') {
        const okAdmin = await verifyAdmin()
        if (!okAdmin) {
          clearAuthState()
          throw new ApiError(403, 'ADMIN_PROFILE_REQUIRED', 'admin profile missing or disabled')
        }
        return
      }
      await refreshMe()
    },
    [refreshMe, verifyAdmin, clearAuthState],
  )

  const logout = useCallback(async () => {
    try {
      await studentService.logout()
    } finally {
      clearAuthState()
    }
  }, [])

  // Phase 5-A：全局 401 → 统一清除登录态，受保护路由自动回登录页
  useEffect(() => {
    const handler = () => {
      clearToken()
      setTokenState(null)
      setAuthUser(null)
      setCurrentUser(null)
    }
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  }, [])

  const value = useMemo(
    () => ({ token, authUser, currentUser, loading, login, logout, refreshMe }),
    [token, authUser, currentUser, loading, login, logout, refreshMe],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
