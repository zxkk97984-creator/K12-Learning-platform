import type { ProfileInsight } from '@/entities/memory/types'
import { SectionCard } from './SectionCard'

interface ChangeCardProps {
  change: ProfileInsight | undefined
}

/** 「最近变化」：仅展示数据库中真实存在的 CHANGE 类型洞察 */
export function ChangeCard({ change }: ChangeCardProps) {
  return (
    <SectionCard title="最近变化">
      {change ? (
        <>
          <blockquote className="border-l-2 border-fg pl-4 font-display text-lg leading-relaxed text-fg">
            {change.description}
          </blockquote>
          <p className="mt-2 font-mono text-[11px] text-muted">
            依据：{change.evidence_ids.length} 条学习证据 · 等级 {change.level}
          </p>
        </>
      ) : (
        <p className="text-sm leading-relaxed text-muted" data-testid="change-empty">
          暂无最近变化——完成更多章节与测验后，这里会展示画像的变化趋势。
        </p>
      )}
    </SectionCard>
  )
}
