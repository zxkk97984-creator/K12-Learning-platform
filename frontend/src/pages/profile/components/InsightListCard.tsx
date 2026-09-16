import { useState } from 'react'

import type { MemoryEvidence, ProfileInsight } from '@/entities/memory/types'
import { INSIGHT_TYPE_LABEL, SOURCE_LABEL, payloadSummary } from '../profile-labels'
import { SectionCard } from './SectionCard'

interface InsightListCardProps {
  insights: ProfileInsight[]
  teacherName: string
  /** 拉取某条洞察的证据（容器注入，便于测试与复用） */
  loadEvidence: (insight: ProfileInsight) => Promise<MemoryEvidence[]>
}

/** 「当前表现」：定性洞察列表，每条可展开真实证据 */
export function InsightListCard({ insights, teacherName, loadEvidence }: InsightListCardProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [evidenceById, setEvidenceById] = useState<Record<string, MemoryEvidence[]>>({})
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [failedId, setFailedId] = useState<string | null>(null)

  const toggle = async (insight: ProfileInsight) => {
    if (expandedId === insight.insight_id) {
      setExpandedId(null)
      return
    }
    setExpandedId(insight.insight_id)
    setFailedId(null)
    if (evidenceById[insight.insight_id]) return
    setLoadingId(insight.insight_id)
    try {
      const evidence = await loadEvidence(insight)
      setEvidenceById((current) => ({ ...current, [insight.insight_id]: evidence }))
    } catch {
      setFailedId(insight.insight_id)
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <SectionCard title="当前表现" flush>
      {insights.length === 0 ? (
        <p className="p-5 text-sm text-muted">
          暂无画像判断。持续学习后，{teacherName}会在这里给出定性观察。
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {insights.map((insight) => {
            const expanded = expandedId === insight.insight_id
            const evidence = evidenceById[insight.insight_id] ?? []
            return (
              <li key={insight.insight_id} className="px-6 py-4">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="rounded-full bg-fg-soft px-2 py-0.5 font-mono text-[10px] text-fg">
                    {INSIGHT_TYPE_LABEL[insight.insight_type] ?? insight.insight_type}
                  </span>
                  <strong className="text-sm text-fg">{insight.dimension}</strong>
                  <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-muted">
                    {insight.level}
                  </span>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    className="ml-auto rounded px-1 py-0.5 text-[11px] text-muted hover:text-fg hover:underline"
                    onClick={() => void toggle(insight)}
                  >
                    {expanded ? '收起' : '为什么？'}
                  </button>
                </div>
                <p className="mt-1.5 max-w-[72ch] text-[13px] leading-relaxed text-muted wrap-anywhere">
                  {insight.description}
                </p>
                {expanded ? (
                  <div className="mt-3 border-t border-border pt-3">
                    <p className="font-mono text-[10px] text-muted">判断依据（真实学习记录）：</p>
                    {loadingId === insight.insight_id ? (
                      <p className="mt-2 text-[11px] text-muted" role="status">正在读取依据…</p>
                    ) : failedId === insight.insight_id ? (
                      <p className="mt-2 text-[11px] text-accent" role="alert">证据详情暂时不可用</p>
                    ) : evidence.length === 0 ? (
                      <p className="mt-2 text-[11px] text-muted">暂无证据记录。</p>
                    ) : (
                      <div className="mt-2 grid gap-2">
                        {evidence.map((item) => (
                          <div key={item.evidence_id} className="rounded-lg bg-fg-soft p-2.5 text-[11px] text-muted">
                            <strong className="text-fg">{SOURCE_LABEL[item.source_type] ?? item.source_type}</strong>
                            <p className="mt-1 break-all">{payloadSummary(item.payload)}</p>
                            <p className="mt-1 font-mono text-[9px]">
                              {item.count} 条事件 · {item.last_occurred_at?.slice(0, 10) ?? '时间未知'}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </SectionCard>
  )
}
