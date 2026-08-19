import { spriteFrames, type CompanionAiState } from '../types'

/** spritesheet 网格（0-B：8 列 × 11 行；资产 spritesheet-extended.webp 当前缺失） */
export const SPRITE_GRID_COLS = 8
export const SPRITE_GRID_ROWS = 11
export const SPRITE_FRAME_MS = 220

/**
 * 计算 spritesheet background-position（真实资产接入时使用；
 * 当前占位渲染不使用，仅保留契约，Phase 11 或资产接入时替换）。
 */
export function spriteBackground(state: CompanionAiState, frame: number): string {
  const spec = spriteFrames[state]
  return `-${frame * 100}% -${(spec.row * 100) / SPRITE_GRID_ROWS}%`
}
