import { describe, expect, it } from 'vitest'

import { deriveStage } from './types'

describe('deriveStage（grade 1~12 → 学段）', () => {
  it('小学 1~6 → PRIMARY（含边界 1/6）', () => {
    expect(deriveStage(1)).toBe('PRIMARY')
    expect(deriveStage(3)).toBe('PRIMARY')
    expect(deriveStage(6)).toBe('PRIMARY')
  })

  it('初中 7~9 → JUNIOR（含边界 7/9）', () => {
    expect(deriveStage(7)).toBe('JUNIOR')
    expect(deriveStage(8)).toBe('JUNIOR')
    expect(deriveStage(9)).toBe('JUNIOR')
  })

  it('高中 10~12 → SENIOR（含边界 10/12）', () => {
    expect(deriveStage(10)).toBe('SENIOR')
    expect(deriveStage(11)).toBe('SENIOR')
    expect(deriveStage(12)).toBe('SENIOR')
  })
})
