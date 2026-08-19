import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import type { StudentProfile } from '@/entities/student/types'
import { clearToken, getToken } from '@/shared/api/auth'
import { ApiError } from '@/shared/api/http'
import { studentService } from '@/mocks/services'

interface AuthContextValue {
  token: string | null
  currentUser: StudentProfile | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [currentUser, setCurrentUser] = useState<StudentProfile | null>(null)
  const [loading, setLoading] = useState(true)

  // 刷新保持登录：恢复 token → 拉当前用户；401 清除（Phase 2 验收「刷新」）
  useEffect(() => {
    const stored = getToken()
    if (!stored) {
      setLoading(false)
      return
    }
    setTokenState(stored)
    studentService
      .getMe()
      .then(setCurrentUser)
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) clearToken()
      })
      .finally(() => setLoading(false))
  }, [])

  const refreshMe = useCallback(async () => {
    const me = await studentService.getMe()
    setCurrentUser(me)
  }, [])

  const login = useCallback(
    async (username: string, password: string) => {
      const dto = await studentService.login(username, password)
      setTokenState(dto.access_token)
      await refreshMe()
    },
    [refreshMe],
  )

  const logout = useCallback(async () => {
    try {
      await studentService.logout()
    } finally {
      clearToken()
      setTokenState(null)
      setCurrentUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ token, currentUser, loading, login, logout, refreshMe }),
    [token, currentUser, loading, login, logout, refreshMe],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
