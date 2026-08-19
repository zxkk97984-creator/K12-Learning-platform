import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ScreenContextProvider } from '@/features/screen-context'

import { queryClient } from './query'

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ScreenContextProvider>{children}</ScreenContextProvider>
    </QueryClientProvider>
  )
}
