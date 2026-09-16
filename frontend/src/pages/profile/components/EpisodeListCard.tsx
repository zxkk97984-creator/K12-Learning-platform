import { useState } from 'react'

import type { StudentEpisode } from '@/entities/memory/types'
import { SectionCard } from './SectionCard'

interface EpisodeListCardProps {
  episodes: StudentEpisode[]
  /** 拉取单个情节详情（容器注入） */
  loadDetail: (episode: StudentEpisode) => Promise<StudentEpisode>
}

const IMPORTANCE_PILL: Record<StudentEpisode['importance'], string> = {
  HIGH: 'border-fg text-fg',
  MEDIUM: 'border-accent text-accent',
  LOW: 'border-border text-muted',
}

/** 「学习情节」：可展开的时间线式情节列表 */
export function EpisodeListCard({ episodes, loadDetail }: EpisodeListCardProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detailById, setDetailById] = useState<Record<string, StudentEpisode>>({})
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [failedId, setFailedId] = useState<string | null>(null)

  const toggle = async (episode: StudentEpisode) => {
    if (expandedId === episode.episode_id) {
      setExpandedId(null)
      return
    }
    setExpandedId(episode.episode_id)
    setFailedId(null)
    if (detailById[episode.episode_id]) return
    setLoadingId(episode.episode_id)
    try {
      const detail = await loadDetail(episode)
      setDetailById((current) => ({ ...current, [episode.episode_id]: detail }))
    } catch {
      setFailedId(episode.episode_id)
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <SectionCard title="学习情节">
      {episodes.length === 0 ? (
        <p className="text-sm text-muted">还没有沉淀出值得记住的学习情节。</p>
      ) : (
        <ul className="grid gap-2">
          {episodes.map((episode) => {
            const expanded = expandedId === episode.episode_id
            const detail = detailById[episode.episode_id]
            return (
              <li key={episode.episode_id} className="rounded-[10px] border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="text-sm text-fg">{episode.title}</strong>
                  <span
                    className={`rounded-full border px-2 py-0.5 font-mono text-[9px] ${IMPORTANCE_PILL[episode.importance]}`}
                  >
                    {episode.importance}
                  </span>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    className="ml-auto rounded px-1 py-0.5 text-[11px] text-muted hover:text-fg hover:underline"
                    onClick={() => void toggle(episode)}
                  >
                    {expanded ? '收起详情' : '详情'}
                  </button>
                </div>
                <p className="mt-1.5 max-w-[72ch] text-[13px] leading-relaxed text-muted wrap-anywhere">
                  {episode.summary}
                </p>
                {expanded ? (
                  <div className="mt-3 border-t border-border pt-3 text-[11px] text-muted">
                    {loadingId === episode.episode_id ? (
                      <p role="status">正在读取情节详情…</p>
                    ) : failedId === episode.episode_id ? (
                      <p role="alert" className="text-accent">情节详情暂时不可用</p>
                    ) : (
                      <div className="grid gap-1.5">
                        <p>
                          发生时间：
                          <time>{detail?.occurred_at.slice(0, 10) ?? episode.occurred_at.slice(0, 10)}</time>
                        </p>
                        <p>关联事件：{detail?.event_ids.length ?? episode.event_ids.length} 条</p>
                        {detail?.tags.length ? <p>标签：{detail.tags.join(' · ')}</p> : null}
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
