import type { CSSProperties } from 'react'

import { useSpriteFrame } from '../hooks/useSpriteFrame'
import { getSpriteStyle, SPRITE_CELL_HEIGHT, SPRITE_CELL_WIDTH } from '../lib/sprite'
import type { CompanionPetId } from '../lib/sprite'
import { useCompanionStore } from '../store/companion-store'
import type { CompanionAiState } from '../types'

interface CompanionSpriteProps {
  state: CompanionAiState
  cellWidth: number
  label: string
  className?: string
  petId?: CompanionPetId
  animated?: boolean
}

export function CompanionSprite({
  state,
  cellWidth,
  label,
  className,
  petId,
  animated = true,
}: CompanionSpriteProps) {
  const frame = useSpriteFrame(state, animated)
  const selectedPetId = useCompanionStore((store) => store.selectedPetId)
  const resolvedPetId = petId ?? selectedPetId
  const cellHeight = Math.round((cellWidth * SPRITE_CELL_HEIGHT) / SPRITE_CELL_WIDTH)
  const style: CSSProperties = {
    display: 'block',
    width: cellWidth,
    height: cellHeight,
    flex: '0 0 auto',
    ...getSpriteStyle(state, frame, cellWidth, resolvedPetId),
  }

  return (
    <span
      className={className}
      role="img"
      aria-label={label}
      data-sprite-state={state}
      data-pet-id={resolvedPetId}
      data-frame={frame}
      style={style}
    />
  )
}
