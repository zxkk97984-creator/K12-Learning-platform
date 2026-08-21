// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { COMPANION_PET_KEY, useCompanionStore } from './companion-store'

describe('companion pet selection', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useCompanionStore.setState({ selectedPetId: 'shuangling' })
  })

  it('persists a selected pet for future visits', () => {
    useCompanionStore.getState().setSelectedPet('lulu-capybara')

    expect(useCompanionStore.getState().selectedPetId).toBe('lulu-capybara')
    expect(window.localStorage.getItem(COMPANION_PET_KEY)).toBe('lulu-capybara')
  })

  it('falls back to Shuangling when an unknown id is selected', () => {
    useCompanionStore.getState().setSelectedPet('not-a-pet')

    expect(useCompanionStore.getState().selectedPetId).toBe('shuangling')
    expect(window.localStorage.getItem(COMPANION_PET_KEY)).toBe('shuangling')
  })

  it('still updates the current pet when browser storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
      throw new DOMException('Storage unavailable')
    })

    expect(() => useCompanionStore.getState().setSelectedPet('shinchan')).not.toThrow()
    expect(useCompanionStore.getState().selectedPetId).toBe('shinchan')
  })
})
