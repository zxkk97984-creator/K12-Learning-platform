import { useRef } from 'react'

import { CompanionDock } from './CompanionDock'
import { CompanionPanel } from './CompanionPanel'

/** 全局桌虫：路由切换常驻（挂载在 AppLayout 的 Outlet 之外） */
export function Companion() {
  const dockRef = useRef<HTMLDivElement>(null)
  return (
    <>
      <CompanionDock dockRef={dockRef} />
      <CompanionPanel dockRef={dockRef} />
    </>
  )
}
