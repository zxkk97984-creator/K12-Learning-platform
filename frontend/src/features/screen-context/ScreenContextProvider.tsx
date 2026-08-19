import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import type { ScreenContext } from './types'

interface ScreenContextValue {
  screenContext: ScreenContext
  setScreenContext: (patch: Partial<ScreenContext>) => void
}

const ScreenContextContext = createContext<ScreenContextValue | null>(null)

const INITIAL_CONTEXT: ScreenContext = { route: '/home', pageType: 'home' }

export function ScreenContextProvider({ children }: { children: ReactNode }) {
  const [screenContext, setScreenContextState] = useState<ScreenContext>(INITIAL_CONTEXT)

  const setScreenContext = useCallback((patch: Partial<ScreenContext>) => {
    setScreenContextState((previous) => ({ ...previous, ...patch }))
  }, [])

  const value = useMemo(
    () => ({ screenContext, setScreenContext }),
    [screenContext, setScreenContext],
  )

  return <ScreenContextContext.Provider value={value}>{children}</ScreenContextContext.Provider>
}

export function useScreenContext(): ScreenContextValue {
  const context = useContext(ScreenContextContext)
  if (!context) throw new Error('useScreenContext must be used within ScreenContextProvider')
  return context
}
