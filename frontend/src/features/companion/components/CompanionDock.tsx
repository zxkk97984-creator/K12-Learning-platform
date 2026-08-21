import type { RefObject } from 'react'

import { useCompanionDock } from '../hooks/useCompanionDock'
import { DOCK_HEIGHT, DOCK_WIDTH } from '../lib/geometry'
import { getCompanionPet } from '../lib/sprite'
import { useCompanionStore } from '../store/companion-store'
import { CompanionSprite } from './CompanionSprite'
import { spriteFrames, stateChipLabels } from '../types'

interface CompanionDockProps {
  dockRef: RefObject<HTMLDivElement | null>
}

export function CompanionDock({ dockRef }: CompanionDockProps) {
  const open = useCompanionStore((state) => state.open)
  const aiState = useCompanionStore((state) => state.aiState)
  const dragging = useCompanionStore((state) => state.dragging)
  const suggest = useCompanionStore((state) => state.suggest)
  const selectedPetId = useCompanionStore((state) => state.selectedPetId)
  const selectedPet = getCompanionPet(selectedPetId)

  const {
    position,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
    handleClick,
    handleKeyDown,
  } = useCompanionDock()

  const scaled = dragging || open || aiState !== 'idle' || suggest
  const statusLabel = suggest
    ? '有一个新建议'
    : stateChipLabels[aiState]

  return (
    <div
      ref={dockRef}
      className="fixed z-40 touch-none select-none"
      style={{ left: position.x, top: position.y, width: DOCK_WIDTH, height: DOCK_HEIGHT }}
      data-open={open}
      data-suggest={suggest}
    >
      <div
        className="h-full w-full transition-transform duration-300 ease-standard hover:scale-100"
        style={{ transform: `scale(${scaled ? 1 : 0.85})`, transformOrigin: 'bottom right' }}
      >
        <button
          type="button"
          className="relative grid h-full w-full place-items-end justify-items-center border-0 bg-transparent p-0"
          aria-label="打开霜铃 AI 教师"
          aria-expanded={open}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          onClick={handleClick}
          onKeyDown={handleKeyDown}
        >
          <span
            className="pointer-events-none absolute -top-1 left-1/2 z-2 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 font-mono text-[8px] whitespace-nowrap text-muted shadow-sm"
            role="status"
          >
            <i className="h-1.5 w-1.5 rounded-full bg-accent" />
            {statusLabel}
          </span>

          <CompanionSprite
            state={aiState}
            cellWidth={122}
            label={`${selectedPet.displayName}${spriteFrames[aiState].label}`}
            className="relative z-1 pointer-events-none"
          />

        </button>
      </div>
    </div>
  )
}
