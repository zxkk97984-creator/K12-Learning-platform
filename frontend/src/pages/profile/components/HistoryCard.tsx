import type { ProfileInsight } from '@/entities/memory/types'
import { INSIGHT_TYPE_LABEL } from '../profile-labels'
import { SectionCard } from './SectionCard'

interface HistoryCardProps {
  historyInsights: ProfileInsight[]
}

/** 「画像版本记录」：被新判断替代的历史版本 */
export function HistoryCard({ historyInsights }: HistoryCardProps) {
  const sorted = [...historyInsights].sort((a, b) => b.valid_from.localeCompare(a.valid_from))
  return (
    <SectionCard title="画像版本记录">
      {sorted.length === 0 ? (
        <p className="text-sm text-muted">还没有被新判断替代的历史版本。</p>
      ) : (
        <ul className="grid gap-2">
          {sorted.map((insight) => (
            <li key={insight.insight_id} className="rounded-[10px] bg-fg-soft p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] text-fg">
                  {INSIGHT_TYPE_LABEL[insight.insight_type] ?? insight.insight_type} · {insight.dimension}
                </span>
                <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[9px] text-muted">
                  {insight.level}
                </span>
                <time className="ml-auto font-mono text-[10px] text-muted">
                  {insight.valid_until?.slice(0, 10) ?? insight.valid_from.slice(0, 10)}
                </time>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{insight.description}</p>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}
