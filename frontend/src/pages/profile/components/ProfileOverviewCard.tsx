import type { ProfileInsight } from '@/entities/memory/types'
import type { StudentPreference } from '@/entities/student/types'
import { DIFFICULTY_LABEL, LENGTH_LABEL, STYLE_LABEL } from '../profile-labels'

interface ProfileOverviewCardProps {
  prefs: StudentPreference
  overview: ProfileInsight | undefined
}

/** 「AI 对我的认识 + 学习方式」合并头卡：陈述与依据全部来自真实 insights */
export function ProfileOverviewCard({ prefs, overview }: ProfileOverviewCardProps) {
  const stats: Array<[string, string]> = [
    ['讲解偏好', STYLE_LABEL[prefs.preferred_explanation_style] ?? prefs.preferred_explanation_style],
    ['学习节奏', LENGTH_LABEL[prefs.preferred_session_length] ?? prefs.preferred_session_length],
    ['难度偏好', DIFFICULTY_LABEL[prefs.preferred_difficulty] ?? prefs.preferred_difficulty],
  ]

  return (
    <article className="rounded-[14px] border border-border bg-surface">
      <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_232px]">
        <div>
          <p className="font-mono text-[10px] text-muted">AI 对我的认识</p>
          {overview ? (
            <>
              <blockquote className="mt-3 max-w-[26ch] font-display text-2xl leading-snug text-fg">
                {overview.dimension} · {overview.level}
              </blockquote>
              <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-muted">
                {overview.description}
              </p>
              <p className="mt-4 border-t border-border pt-3 font-mono text-[11px] leading-relaxed text-muted">
                依据：{overview.evidence_ids.length} 条学习证据（可在下方展开查看）
              </p>
            </>
          ) : (
            <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-muted" data-testid="overview-empty">
              暂无画像判断——随着对话、阅读和测验的积累，这里会展示 AI 对你的认识。
            </p>
          )}
        </div>
        <dl className="grid content-start gap-0 divide-y divide-border rounded-[10px] bg-fg-soft px-4">
          {stats.map(([label, value]) => (
            <div key={label} className="py-3 first:pt-1 last:pb-1">
              <dt className="font-mono text-[9px] tracking-wider text-muted">{label}</dt>
              <dd className="mt-1 text-sm font-semibold text-fg">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </article>
  )
}
