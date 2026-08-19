import { create } from 'zustand'

import {
  clampDock,
  COMPANION_POSITION_KEY,
  defaultDockPosition,
  type Point,
} from '../lib/geometry'
import type { CompanionAiState } from '../types'

function loadPosition(): Point {
  if (typeof window === 'undefined') return { x: 0, y: 0 }
  try {
    const saved = window.localStorage.getItem(COMPANION_POSITION_KEY)
    if (saved) {
      const parsed = JSON.parse(saved) as Partial<Point>
      if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
        return clampDock(parsed.x, parsed.y)
      }
    }
  } catch {
    // 损坏数据走默认位置
  }
  return defaultDockPosition()
}

export function persistPosition(position: Point): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(COMPANION_POSITION_KEY, JSON.stringify(position))
}

interface CompanionStore {
  open: boolean
  position: Point
  aiState: CompanionAiState
  dragging: boolean
  suggest: boolean
  setOpen: (open: boolean) => void
  toggleOpen: () => void
  setPosition: (position: Point) => void
  setAiState: (state: CompanionAiState) => void
  setDragging: (dragging: boolean) => void
  setSuggest: (suggest: boolean) => void
}

export const useCompanionStore = create<CompanionStore>()((set) => ({
  open: false,
  position: loadPosition(),
  aiState: 'idle',
  dragging: false,
  suggest: false,
  setOpen: (open) => set({ open }),
  toggleOpen: () => set((state) => ({ open: !state.open })),
  setPosition: (position) => set({ position }),
  setAiState: (aiState) => set({ aiState }),
  setDragging: (dragging) => set({ dragging }),
  setSuggest: (suggest) => set({ suggest }),
}))
