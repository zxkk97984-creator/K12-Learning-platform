import { NavLink } from 'react-router-dom'

const BOTTOM_ITEMS = [
  { to: '/home', label: '首页', icon: '⌂' },
  { to: '/library', label: '学习', icon: '▤' },
  { to: '/quizzes', label: '练习', icon: '✓' },
  { to: '/profile', label: '成长', icon: '◔' },
] as const

/** <820px 底部四项导航（T17 §5.2）。safe-area 加高，页底 padding 由上层保证不遮挡。 */
export function BottomNav() {
  return (
    <nav
      aria-label="底部主导航"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-bg/90 backdrop-blur md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="mx-auto grid max-w-[var(--content)] grid-cols-4 px-2">
        {BOTTOM_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                'flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-xs',
                isActive ? 'font-semibold text-accent' : 'text-muted',
              ].join(' ')
            }
          >
            <span className="text-base leading-none" aria-hidden="true">
              {item.icon}
            </span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
