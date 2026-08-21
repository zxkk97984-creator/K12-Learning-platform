import { describe, expect, it } from 'vitest'

import { spriteFrames } from '../types'
import { COMPANION_PETS, getCompanionPet, getSpriteStyle } from './sprite'

describe('companion sprite contract', () => {
  it('offers Shuangling plus the five imported desktop pets', () => {
    expect(COMPANION_PETS.map((pet) => pet.id)).toEqual([
      'shuangling',
      'anya',
      'doraemon',
      'kun-like',
      'lulu-capybara',
      'shinchan',
    ])
    expect(getCompanionPet('unknown').id).toBe('shuangling')
    expect(spriteFrames.idle).toMatchObject({ row: 0, frames: 6 })
    expect(spriteFrames['running-right']).toMatchObject({ row: 1, frames: 8 })
    expect(spriteFrames['running-left']).toMatchObject({ row: 2, frames: 8 })
  })

  it('computes pixel-perfect background offsets for a rendered cell', () => {
    expect(getSpriteStyle('running-left', 7, 122, 'shuangling')).toEqual({
      backgroundImage: 'url(/spritesheet-extended.webp)',
      backgroundRepeat: 'no-repeat',
      backgroundSize: '976px 1452px',
      backgroundPosition: '-854px -264px',
    })
  })

  it('uses the source atlas row count for imported 8x9 pets', () => {
    expect(getSpriteStyle('idle', 0, 122, 'anya')).toEqual({
      backgroundImage: 'url(/pets/anya/spritesheet.webp)',
      backgroundRepeat: 'no-repeat',
      backgroundSize: '976px 1188px',
      backgroundPosition: '0px 0px',
    })
  })
})
