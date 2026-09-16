import type { Book, BookProgress, Chapter } from '@/entities/book/types'
import { useTeacherName } from '@/features/companion'

interface ContinueLearningCardProps {
  loading: boolean
  error: boolean
  progress: BookProgress | null
  book: Book | null
  chapter: Chapter | null
  onContinue: () => void
  onStart: () => void
  onChat: () => void
}

/** T08 唯一主学习卡：加载/空态/失败/进行中四态，仅一个主行动。 */
export function ContinueLearningCard({
  loading,
  error,
  progress,
  book,
  chapter,
  onContinue,
  onStart,
  onChat,
}: ContinueLearningCardProps) {
  const teacherName = useTeacherName()

  if (loading) {
    return (
      <div className="grid min-h-[232px] place-items-center p-8 text-center" data-testid="continue-loading">
        <p className="text-sm text-muted">正在恢复继续学习记录…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="grid min-h-[232px] place-items-center p-8 text-center" data-testid="continue-error">
        <div>
          <h3 className="font-display text-xl text-fg">暂时无法读取上次进度</h3>
          <p className="mt-2 max-w-[40ch] text-sm text-muted">请稍后重试，或直接从书库开始。</p>
          <button
            type="button"
            className="mt-4 rounded-[10px] border border-border bg-surface px-4 py-2 text-sm text-fg hover:border-fg"
            onClick={onStart}
          >
            去书库看看
          </button>
        </div>
      </div>
    )
  }

  // 有进度：主卡显示书名/章节/位置 + 唯一"继续学习"主行动。
  if (progress && book && chapter) {
    const progressTime = progress.last_read_at
      ? new Date(progress.last_read_at).toLocaleString('zh-CN', {
          month: 'numeric',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })
      : null
    const completed = progress.status === 'COMPLETED'
    return (
      <div className="overflow-hidden rounded-[22px] border border-border bg-surface" data-testid="continue-learning">
        <div className="grid min-h-[132px] place-items-center bg-fg p-5 text-center">
          <strong className="font-display text-2xl leading-tight text-surface">{book.title}</strong>
          {book.description ? (
            <span className="mt-1 block max-w-[42ch] text-xs text-surface/70">{book.description}</span>
          ) : null}
        </div>
        <div className="p-5">
          <h2 className="font-display text-xl leading-snug text-fg">
            {completed ? (
              <>上一章已完成 · {chapter.title}</>
            ) : (
              <>第 {chapter.chapter_order} 章 · {chapter.title}</>
            )}
          </h2>
          {!completed && typeof progress.position_percent === 'number' ? (
            <p className="mt-1 font-mono text-xs text-muted">{progress.position_percent}%</p>
          ) : null}
          <p className="mt-2 max-w-[64ch] text-sm leading-relaxed text-muted">
            {chapter.summary ?? ''}
          </p>
          <p className="mt-3 text-xs text-muted">
            {progressTime ? `最近阅读 ${progressTime}` : '暂无阅读时间'}
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              data-testid="continue-learning-action"
              className="rounded-[10px] bg-accent px-4 py-2.5 text-sm text-surface hover:bg-accent/85"
              onClick={onContinue}
            >
              {completed ? '继续下一章 →' : `继续第 ${chapter.chapter_order} 章 →`}
            </button>
            <button
              type="button"
              aria-label={`和${teacherName}聊两句`}
              className="rounded-[10px] border border-border bg-surface px-4 py-2.5 text-sm text-fg hover:border-fg"
              onClick={onChat}
            >
              和{teacherName}聊两句
            </button>
          </div>
        </div>
      </div>
    )
  }

  // 无进度（新用户）：主卡引导选一门适合的课。
  return (
    <div className="grid min-h-[232px] place-items-center p-8 text-center" data-testid="continue-empty">
      <div>
        <p className="text-sm text-muted">还没有开始学习</p>
        <h3 className="mt-2 font-display text-xl text-fg">选一门适合你的课程</h3>
        <p className="mt-2 max-w-[40ch] text-sm text-muted">
          内容按你的年级和兴趣整理，{teacherName}会记住你停在哪里。
        </p>
        <button
          type="button"
          className="mt-4 rounded-[10px] bg-accent px-4 py-2 text-sm text-surface"
          onClick={onStart}
        >
          去书库看看
        </button>
      </div>
    </div>
  )
}
