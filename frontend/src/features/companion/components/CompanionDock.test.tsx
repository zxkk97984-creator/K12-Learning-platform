// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { CompanionDock } from './CompanionDock'
import { useCompanionStore } from '../store/companion-store'

describe('CompanionDock', () => {
  beforeEach(() => {
    useCompanionStore.setState({ aiState: 'idle', dragging: false, open: false, suggest: false })
    Object.defineProperty(HTMLButtonElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: () => undefined,
    })
  })

  afterEach(() => cleanup())

  it('renders the Shuangling sprite instead of the moon placeholder', () => {
    const dockRef = { current: null }
    render(<CompanionDock dockRef={dockRef} />)

    expect(screen.getByRole('img', { name: '霜铃待机中' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('在线 · 随时可以问我')
    expect(screen.queryByText('🌙')).toBeNull()
  })

  it('plays the matching running row while dragging and restores the AI state on release', () => {
    const dockRef = { current: null }
    render(<CompanionDock dockRef={dockRef} />)
    const button = screen.getByRole('button', { name: '打开霜铃 AI 教师' })
    const sprite = () => screen.getByRole('img')

    fireEvent.pointerDown(button, { pointerId: 1, clientX: 100, clientY: 100 })
    fireEvent.pointerMove(button, { pointerId: 1, clientX: 140, clientY: 100 })
    expect(sprite().getAttribute('data-sprite-state')).toBe('running-right')

    fireEvent.pointerUp(button, { pointerId: 1 })
    expect(sprite().getAttribute('data-sprite-state')).toBe('idle')

    fireEvent.pointerDown(button, { pointerId: 2, clientX: 200, clientY: 100 })
    fireEvent.pointerMove(button, { pointerId: 2, clientX: 160, clientY: 100 })
    expect(sprite().getAttribute('data-sprite-state')).toBe('running-left')

    fireEvent.pointerUp(button, { pointerId: 2 })
    expect(sprite().getAttribute('data-sprite-state')).toBe('idle')
  })
})
