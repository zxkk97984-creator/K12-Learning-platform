import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { useScreenContext } from './ScreenContextProvider'

/**
 * 路由切换时清理上一页面的 ScreenContext 残留（Phase 2-A3）。
 *
 * 时序保证：React passive effect 自底向上执行——新页面若在自身 effect 中
 * 声明了上下文（如 ReaderPage），其 route 已等于当前 pathname，本组件的
 * 函数式 reset 会自动跳过；只有「目标页面不声明上下文」时才真正清空，
 * 从而杜绝离开 Reader 后仍携带旧 book/chapter 的问题。
 */
export function ScreenContextRouteSync() {
  const location = useLocation()
  const { resetScreenContext } = useScreenContext()

  useEffect(() => {
    resetScreenContext(location.pathname)
  }, [location.pathname, resetScreenContext])

  return null
}
