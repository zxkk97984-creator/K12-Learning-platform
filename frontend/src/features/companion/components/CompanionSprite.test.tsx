// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { CompanionSprite } from './CompanionSprite'

describe('CompanionSprite', () => {
  afterEach(() => cleanup())

  it('renders the transparent spritesheet cell with an accessible label', () => {
    render(<CompanionSprite state="idle" cellWidth={122} label="霜铃待机" />)

    const sprite = screen.getByRole('img', { name: '霜铃待机' })
    expect(sprite.getAttribute('data-sprite-state')).toBe('idle')
    expect(sprite.getAttribute('data-frame')).toBe('0')
    expect(sprite.style.width).toBe('122px')
    expect(sprite.style.height).toBe('132px')
    expect(sprite.style.backgroundImage).toBe('url("/spritesheet-extended.webp")')
    expect(sprite.style.backgroundPosition).toBe('0px 0px')
    expect(sprite.textContent).toBe('')
  })

  it('renders a selected imported pet with its own atlas', () => {
    render(<CompanionSprite state="idle" cellWidth={122} label="阿尼亚待机" petId="anya" />)

    const sprite = screen.getByRole('img', { name: '阿尼亚待机' })
    expect(sprite.getAttribute('data-pet-id')).toBe('anya')
    expect(sprite.style.backgroundImage).toBe('url("/pets/anya/spritesheet.webp")')
    expect(sprite.style.backgroundSize).toBe('976px 1188px')
  })
})
