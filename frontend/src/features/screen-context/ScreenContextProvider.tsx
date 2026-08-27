import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { derivePageType, type ScreenContext } from './types'

interface ScreenContextValue {
  screenContext: ScreenContext
  setScreenContext: (patch: Partial<ScreenContext>) => void
  /** 整体重置到指定路由的干净上下文（路由切换时清理上一页残留）。 */
  resetScreenContext: (route: string) => void
}

const ScreenContextContext = createContext<ScreenContextValue | null>(null)

const INITIAL_CONTEXT: ScreenContext = { route: '/home', pageType: 'home' }

export function ScreenContextProvider({ children }: { children: ReactNode }) {
  const [screenContext, setScreenContextState] = useState<ScreenContext>(INITIAL_CONTEXT)

  const setScreenContext = useCallback((patch: Partial<ScreenContext>) => {
    setScreenContextState((previous) => ({ ...previous, ...patch }))
  }, [])

  // 函数式更新读取最新状态：页面 effect 先于路由同步 effect 执行时，
  // 若新页面已声明自己的 route，这里不会误清它的上下文。
  const resetScreenContext = useCallback((route: string) => {
    setScreenContextState((previous) =>
      previous.route === route
        ? previous
        : { route, pageType: derivePageType(route) },
    )
  }, [])

  const value = useMemo(
    () => ({ screenContext, setScreenContext, resetScreenContext }),
    [screenContext, setScreenContext, resetScreenContext],
  )

  return <ScreenContextContext.Provider value={value}>{children}</ScreenContextContext.Provider>
}

export function useScreenContext(): ScreenContextValue {
  const context = useContext(ScreenContextContext)
  if (!context) throw new Error('useScreenContext must be used within ScreenContextProvider')
  return context
}
