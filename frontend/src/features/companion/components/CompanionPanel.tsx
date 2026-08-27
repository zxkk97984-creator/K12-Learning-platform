import { useEffect, useState, type RefObject } from 'react'

import { ConversationPanelContent } from '@/features/conversation'

import { placePanel, type PanelRect } from '../lib/geometry'
import { getCompanionPet } from '../lib/sprite'
import { useCompanionStore, useTeacherName } from '../store/companion-store'
import { spriteFrames } from '../types'
import { CompanionSprite } from './CompanionSprite'

interface CompanionPanelProps {
  dockRef: RefObject<HTMLDivElement | null>
}

/** 面板定位骨架：内容（聊天/quiz 卡）由 1-F 实现 */
export function CompanionPanel({ dockRef }: CompanionPanelProps) {
  const open = useCompanionStore((state) => state.open)
  const position = useCompanionStore((state) => state.position)
  const aiState = useCompanionStore((state) => state.aiState)
  const selectedPetId = useCompanionStore((state) => state.selectedPetId)
  const selectedPet = getCompanionPet(selectedPetId)
  const teacherName = useTeacherName()
  const setOpen = useCompanionStore((state) => state.setOpen)
  const setAiState = useCompanionStore((state) => state.setAiState)
  const [rect, setRect] = useState<PanelRect | null>(null)

  useEffect(() => {
    if (!open || !dockRef.current) return
    const update = () => {
      const dockRect = dockRef.current?.getBoundingClientRect()
      if (dockRect) setRect(placePanel(dockRect))
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [open, position, dockRef])

  if (!open || !rect) return null

  return (
    <aside
      className="fixed z-35 flex flex-col overflow-hidden rounded-[18px] border border-fg bg-surface shadow-soft"
      style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
      aria-label={`${teacherName}对话面板`}
      data-open="true"
    >
      <div className="flex min-h-[67px] items-center justify-between border-b border-border px-4">
        <div className="flex min-w-0 items-center gap-2">
          <div className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full bg-fg-soft">
            <CompanionSprite
              state={aiState}
              cellWidth={33}
              label={`${selectedPet.displayName}${spriteFrames[aiState].label}`}
              animated={false}
              className="pointer-events-none"
            />
          </div>
          <div className="min-w-0">
            <strong className="font-display text-sm">{teacherName}</strong>
            <span className="ml-2 text-[10px] text-muted">对话面板骨架 · 1-F 填充聊天内容</span>
          </div>
        </div>
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-[9px] text-muted hover:bg-fg-soft hover:text-fg"
          aria-label="收起对话"
          onClick={() => {
            setOpen(false)
            setAiState('idle')
          }}
        >
          ✕
        </button>
      </div>
      <ConversationPanelContent />
    </aside>
  )
}
