import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { AuthProvider } from '@/features/auth'
import { ScreenContextProvider } from '@/features/screen-context'

import { queryClient } from './query'

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ScreenContextProvider>{children}</ScreenContextProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
