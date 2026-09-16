import type { RefObject } from 'react'

import { useCompanionDock } from '../hooks/useCompanionDock'
import { DOCK_HEIGHT, DOCK_WIDTH } from '../lib/geometry'
import { getCompanionPet } from '../lib/sprite'
import { useCompanionStore, useTeacherName } from '../store/companion-store'
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
  const teacherName = useTeacherName()

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
      className="pointer-events-none fixed z-40 touch-none select-none"
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
          data-companion-toggle
          // T25：dock 是常驻浮动层，尺寸固定 140×168；把可点击命中区收窄到精灵本体，
          // 让透明边距对底层页面内容"透传"，避免盖住设置页等处的"保存设置"主按钮。
          // 容器用 pointer-events-none，仅按钮恢复 auto（拖拽仍走按钮指针事件）。
          className="pointer-events-auto relative grid h-auto w-auto min-h-[64px] min-w-[96px] place-items-end justify-items-center border-0 bg-transparent p-0"
          aria-label={`打开${teacherName} AI 教师`}
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
