import {
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import {
  clampDock,
  COMPANION_POSITION_KEY,
  DOCK_DRAG_THRESHOLD,
  DOCK_KEYBOARD_STEP,
  type Point,
} from '../lib/geometry'
import { persistPosition, useCompanionStore } from '../store/companion-store'

interface DragState {
  startX: number
  startY: number
  originX: number
  originY: number
  moved: boolean
}

/** 桌虫拖拽 / 键盘 / resize / Escape / 主动建议 */
export function useCompanionDock() {
  const position = useCompanionStore((state) => state.position)
  const open = useCompanionStore((state) => state.open)
  const setPosition = useCompanionStore((state) => state.setPosition)
  const setDragging = useCompanionStore((state) => state.setDragging)
  const setOpen = useCompanionStore((state) => state.setOpen)
  const setSuggest = useCompanionStore((state) => state.setSuggest)

  const dragRef = useRef<DragState | null>(null)
  const positionRef = useRef<Point>(position)

  useEffect(() => {
    positionRef.current = position
  }, [position])

  // window resize：重新 clamp（对齐原型）
  useEffect(() => {
    const onResize = () => {
      const next = clampDock(positionRef.current.x, positionRef.current.y)
      positionRef.current = next
      setPosition(next)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [setPosition])

  // Escape：全局关闭面板
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape' && useCompanionStore.getState().open) {
        useCompanionStore.getState().setOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // 主动建议：加载 6s 后提示、7s 恢复；面板打开时跳过/清除
  useEffect(() => {
    if (open) {
      setSuggest(false)
      return
    }
    const showTimer = window.setTimeout(() => setSuggest(true), 6000)
    const hideTimer = window.setTimeout(() => setSuggest(false), 13000)
    return () => {
      window.clearTimeout(showTimer)
      window.clearTimeout(hideTimer)
    }
  }, [open, setSuggest])

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    dragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: positionRef.current.x,
      originY: positionRef.current.y,
      moved: false,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const dx = event.clientX - drag.startX
    const dy = event.clientY - drag.startY
    if (Math.abs(dx) + Math.abs(dy) > DOCK_DRAG_THRESHOLD) drag.moved = true
    if (!drag.moved) return
    setDragging(true)
    const next = clampDock(drag.originX + dx, drag.originY + dy)
    positionRef.current = next
    setPosition(next)
  }

  const handlePointerUp = () => {
    const drag = dragRef.current
    if (!drag) return
    if (drag.moved) persistPosition(positionRef.current)
    setDragging(false)
  }

  const handleClick = () => {
    if (dragRef.current?.moved) {
      dragRef.current = null
      return
    }
    dragRef.current = null
    setOpen(!useCompanionStore.getState().open)
  }

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    const movement: Partial<Record<string, Point>> = {
      ArrowLeft: { x: -DOCK_KEYBOARD_STEP, y: 0 },
      ArrowRight: { x: DOCK_KEYBOARD_STEP, y: 0 },
      ArrowUp: { x: 0, y: -DOCK_KEYBOARD_STEP },
      ArrowDown: { x: 0, y: DOCK_KEYBOARD_STEP },
    }
    const delta = movement[event.key]
    if (!delta) return
    event.preventDefault()
    const next = clampDock(positionRef.current.x + delta.x, positionRef.current.y + delta.y)
    positionRef.current = next
    setPosition(next)
    persistPosition(next)
  }

  return { position, handlePointerDown, handlePointerMove, handlePointerUp, handleClick, handleKeyDown }
}

export { COMPANION_POSITION_KEY }
