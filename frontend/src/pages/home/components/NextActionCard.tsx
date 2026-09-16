import type { LearningNextAction } from '@/shared/api/recommendation-service'

interface NextActionCardProps {
  action?: LearningNextAction
  loading: boolean
  onOpen: (action: LearningNextAction) => void
  /** 跳过复习（用户可暂时跳过） */
  onSkip?: () => void
}

/** §6.1 统一下一步行动卡：单个行动目标，避免首页推荐/继续学习入口重复。 */
export function NextActionCard({ action, loading, onOpen, onSkip }: NextActionCardProps) {
  return (
    <div className="rounded-[14px] border border-border bg-surface p-4">
      <p className="font-mono text-[10px] tracking-widest text-muted">下一步行动</p>
      {loading || !action ? (
        <p className="mt-2 text-sm text-muted">正在计算下一步…</p>
      ) : (
        <>
          <h3 className="mt-2 font-display text-xl text-fg">{action.label}</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">{action.reason}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded-[10px] bg-accent px-3 py-2 text-xs text-surface hover:bg-accent/85"
              onClick={() => onOpen(action)}
            >
              {action.type === 'REVIEW_QUIZ' ? '去回顾' : '去做'} →
            </button>
            {action.type === 'REVIEW_QUIZ' && onSkip ? (
              <button
                type="button"
                className="rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-muted hover:border-fg"
                onClick={onSkip}
              >
                暂时跳过
              </button>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}
