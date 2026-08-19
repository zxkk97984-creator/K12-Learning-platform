import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clampDock, placePanel } from './geometry'

function stubWindow(width: number, height: number): void {
  vi.stubGlobal('window', { innerWidth: width, innerHeight: height })
}

describe('clampDock（Safe Zone）', () => {
  beforeEach(() => stubWindow(1440, 900))
  afterEach(() => vi.unstubAllGlobals())

  it('越界时钳到 Safe Zone 边界（x∈[12, w-134]、y∈[76, h-160]）', () => {
    expect(clampDock(0, 0)).toEqual({ x: 12, y: 76 })
    expect(clampDock(5000, 5000)).toEqual({ x: 1306, y: 740 })
  })

  it('范围内原样返回', () => {
    expect(clampDock(300, 200)).toEqual({ x: 300, y: 200 })
  })

  it('小视口下边界下限优先（max(12, w-134)）', () => {
    stubWindow(100, 100)
    expect(clampDock(0, 0)).toEqual({ x: 12, y: 76 })
    expect(clampDock(9999, 9999)).toEqual({ x: 12, y: 76 })
  })
})

describe('placePanel（右侧优先 → 翻左 → 底部抽屉）', () => {
  beforeEach(() => stubWindow(1440, 900))
  afterEach(() => vi.unstubAllGlobals())

  const dockRect = (left: number, top: number): DOMRect =>
    ({
      left,
      top,
      right: left + 140,
      bottom: top + 168,
      width: 140,
      height: 168,
    }) as DOMRect

  it('右侧空间足够 → 面板出现在 dock 右侧', () => {
    const rect = placePanel(dockRect(100, 100))
    expect(rect.left).toBe(256) // 100+140+16
    expect(rect.top).toBe(76) // 100+168-640=-372 → 钳到 76
    expect(rect.width).toBe(392)
    expect(rect.height).toBe(640)
  })

  it('右侧溢出且左侧空间足够 → 翻到左侧', () => {
    const rect = placePanel(dockRect(1200, 500))
    expect(rect.left).toBe(1200 - 392 - 16)
    expect(rect.top).toBe(76)
  })

  it('右侧与左侧都不足 → 钳到视口内', () => {
    const rect = placePanel(dockRect(500, 500))
    expect(rect.left + rect.width).toBeLessThanOrEqual(1424)
    expect(rect.left).toBeGreaterThanOrEqual(16)
  })

  it('≤720px → 底部抽屉（width 100vw-32、left 16、top 贴底）', () => {
    stubWindow(700, 800)
    const rect = placePanel(dockRect(500, 500))
    expect(rect.width).toBe(392)
    expect(rect.height).toBe(640)
    expect(rect.left).toBe(16)
    expect(rect.top).toBe(144) // 800-640-16
  })
})
