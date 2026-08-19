import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  { to: '/admin', label: '总览', end: true },
  { to: '/admin/books', label: '书籍', end: false },
  { to: '/admin/knowledge', label: '知识库', end: false },
]

export function AdminLayout() {
  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">管理后台</p>
      <h1 className="mt-3 font-display text-4xl text-fg">平台维护</h1>
      <nav className="mt-5 flex gap-1.5" aria-label="管理导航">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              [
                'rounded-[10px] px-3.5 py-2 text-sm',
                isActive
                  ? 'border border-border bg-surface text-fg shadow-sm'
                  : 'text-muted hover:bg-fg-soft hover:text-fg',
              ].join(' ')
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-6">
        <Outlet />
      </div>
    </section>
  )
}
