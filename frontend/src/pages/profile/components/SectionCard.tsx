import type { ReactNode } from 'react'

interface SectionCardProps {
  title: string
  children: ReactNode
  /** true 时正文无内边距，由列表项自带（通栏分隔线列表用） */
  flush?: boolean
}

export function SectionCard({ title, children, flush = false }: SectionCardProps) {
  return (
    <article className="overflow-hidden rounded-[14px] border border-border bg-surface">
      <h2 className="border-b border-border px-6 py-3.5 font-display text-lg text-fg">{title}</h2>
      <div className={flush ? '' : 'p-5'}>{children}</div>
    </article>
  )
}
