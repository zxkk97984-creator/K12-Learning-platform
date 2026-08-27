import { create } from 'zustand'

import {
  clampDock,
  COMPANION_POSITION_KEY,
  defaultDockPosition,
  type Point,
} from '../lib/geometry'
import type { CompanionAiState } from '../types'
import { getCompanionPet, type CompanionPetId } from '../lib/sprite'

export const COMPANION_PET_KEY = 'shuangling-companion-pet'

function loadPetId(): CompanionPetId {
  if (typeof window === 'undefined') return 'shuangling'
  try {
    return getCompanionPet(window.localStorage.getItem(COMPANION_PET_KEY) ?? '').id
  } catch {
    return 'shuangling'
  }
}

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

/** 当前桌宠对应的 AI 教师名字（组件内使用，随桌宠切换自动更新） */
export function useTeacherName(): string {
  const selectedPetId = useCompanionStore((state) => state.selectedPetId)
  return getCompanionPet(selectedPetId).displayName
}

/** 当前桌宠对应的 AI 教师名字（store/非组件上下文使用） */
export function currentTeacherName(): string {
  return getCompanionPet(useCompanionStore.getState().selectedPetId).displayName
}

interface CompanionStore {
  open: boolean
  position: Point
  aiState: CompanionAiState
  dragging: boolean
  suggest: boolean
  selectedPetId: CompanionPetId
  setOpen: (open: boolean) => void
  toggleOpen: () => void
  setPosition: (position: Point) => void
  setAiState: (state: CompanionAiState) => void
  setDragging: (dragging: boolean) => void
  setSuggest: (suggest: boolean) => void
  setSelectedPet: (petId: string) => void
}

export const useCompanionStore = create<CompanionStore>()((set) => ({
  open: false,
  position: loadPosition(),
  aiState: 'idle',
  dragging: false,
  suggest: false,
  selectedPetId: loadPetId(),
  setOpen: (open) => set({ open }),
  toggleOpen: () => set((state) => ({ open: !state.open })),
  setPosition: (position) => set({ position }),
  setAiState: (aiState) => set({ aiState }),
  setDragging: (dragging) => set({ dragging }),
  setSuggest: (suggest) => set({ suggest }),
  setSelectedPet: (petId) => {
    const selectedPetId = getCompanionPet(petId).id
    try {
      window.localStorage.setItem(COMPANION_PET_KEY, selectedPetId)
    } catch {
      // 存储不可用时仍允许本次会话切换桌宠。
    }
    set({ selectedPetId })
  },
}))
