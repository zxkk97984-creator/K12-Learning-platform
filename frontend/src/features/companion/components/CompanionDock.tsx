import type { RefObject } from 'react'

import { useCompanionDock } from '../hooks/useCompanionDock'
import { useSpriteFrame } from '../hooks/useSpriteFrame'
import { DOCK_HEIGHT, DOCK_WIDTH } from '../lib/geometry'
import { useCompanionStore } from '../store/companion-store'
import { spriteFrames, stateChipLabels, stateEmoji, type CompanionAiState } from '../types'

interface CompanionDockProps {
  dockRef: RefObject<HTMLDivElement | null>
}

export function CompanionDock({ dockRef }: CompanionDockProps) {
  const open = useCompanionStore((state) => state.open)
  const aiState = useCompanionStore((state) => state.aiState)
  const dragging = useCompanionStore((state) => state.dragging)
  const suggest = useCompanionStore((state) => state.suggest)
  const frame = useSpriteFrame(aiState)

  const {
    position,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleClick,
    handleKeyDown,
  } = useCompanionDock()

  const scaled = dragging || open || aiState !== 'idle' || suggest

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
          onClick={handleClick}
          onKeyDown={handleKeyDown}
        >
          <span
            className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 rounded-full bg-fg px-2.5 py-1 text-[10px] whitespace-nowrap text-surface transition-opacity"
            style={{ opacity: aiState !== 'idle' || suggest ? 1 : 0 }}
            role="status"
          >
            {suggest ? '有一个新建议' : spriteFrames[aiState].label}
          </span>

          {/* sprite 占位：真实 spritesheet（spritesheet-extended.webp）资产缺失，
              以渐变圆形 + emoji + 帧号呈现状态变化；Phase 11 / 资产接入时替换 */}
          <span
            className={`relative z-1 grid h-32 w-32 place-items-center rounded-full text-5xl ${
              aiState === 'speaking' ? 'animate-pulse' : ''
            }`}
            style={{
              background:
                'radial-gradient(circle at 35% 30%, var(--color-accent-soft), var(--color-accent))',
              boxShadow: 'var(--shadow-soft)',
            }}
            data-sprite-state={aiState}
            data-frame={frame}
          >
            {stateEmoji[aiState as CompanionAiState]}
            <span className="absolute bottom-1 font-mono text-[9px] text-surface/80">
              {frame + 1}/{spriteFrames[aiState].frames}
            </span>
          </span>

          <span className="pointer-events-none absolute bottom-1 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 font-mono text-[8px] whitespace-nowrap text-muted shadow-sm transition-opacity">
            <i className="h-1.5 w-1.5 rounded-full bg-accent" />
            {stateChipLabels[aiState]}
          </span>
        </button>
      </div>
    </div>
  )
}
