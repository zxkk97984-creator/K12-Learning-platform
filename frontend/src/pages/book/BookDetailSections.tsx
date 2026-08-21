import type { Book, BookProgress, Chapter, KnowledgePoint } from '@/entities/book/types'

const TINT_GRADIENT: Record<NonNullable<Book['tint']>, string> = {
  1: 'linear-gradient(135deg, oklch(88% 0.08 250), oklch(64% 0.12 250))',
  2: 'linear-gradient(135deg, oklch(88% 0.08 160), oklch(64% 0.12 160))',
  3: 'linear-gradient(135deg, oklch(89% 0.07 55), oklch(66% 0.1 55))',
  4: 'linear-gradient(135deg, oklch(88% 0.08 330), oklch(64% 0.12 330))',
}

const PROGRESS_STATUS: Record<BookProgress['status'], string> = {
  NOT_STARTED: '未开始',
  READING: '阅读中',
  COMPLETED: '已完成',
}

export function BookCover({ book }: { book: Book }) {
  const tint = book.tint ?? 1

  return (
    <div className="relative aspect-[4/5] overflow-hidden rounded-[14px] border border-border bg-fg-soft">
      {book.cover_url ? (
        <img
          src={book.cover_url}
          alt={`${book.title}封面`}
          className="h-full w-full object-cover"
        />
      ) : (
        <div
          className="flex h-full flex-col justify-between p-5 text-fg"
          style={{ backgroundImage: TINT_GRADIENT[tint] }}
        >
          <span className="font-mono text-xs tracking-[0.18em] opacity-65">
            {book.book_no ?? 'BOOK'}
          </span>
          <div>
            <span className="font-mono text-[10px] tracking-wider opacity-70">
              {book.tags[0] ?? '学习内容'}
            </span>
            <strong className="mt-2 block max-w-[12ch] font-display text-3xl leading-tight">
              {book.title}
            </strong>
          </div>
        </div>
      )}
    </div>
  )
}

export function ProgressPanel({
  progress,
  chapterTitle,
  unavailable = false,
}: {
  progress: BookProgress | null
  chapterTitle?: string
  unavailable?: boolean
}) {
  const position = progress
    ? Math.max(0, Math.min(100, Math.round(progress.position_percent)))
    : 0

  return (
    <section aria-labelledby="progress-heading" className="rounded-[14px] border border-border bg-surface p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="progress-heading" className="font-display text-xl text-fg">
          学习进度
        </h2>
        <span className="font-mono text-[10px] text-muted">
          {unavailable ? '暂不可用' : progress ? `${position}%` : '未开始'}
        </span>
      </div>
      {unavailable ? (
        <p className="mt-3 text-sm text-muted">暂时无法读取学习记录，开始学习后会自动保存。</p>
      ) : progress ? (
        <>
          <div
            role="progressbar"
            aria-label="本书学习进度"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={position}
            className="mt-4 h-2 overflow-hidden rounded-full bg-fg-soft"
          >
            <div className="h-full rounded-full bg-accent" style={{ width: `${position}%` }} />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
            <span>{PROGRESS_STATUS[progress.status]}</span>
            {chapterTitle ? (
              <>
                <span aria-hidden="true">·</span>
                <span>继续：{chapterTitle}</span>
              </>
            ) : null}
          </div>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted">还没有开始这本书，准备好就从第一章出发吧。</p>
      )}
    </section>
  )
}

export function ChaptersSection({
  chapters,
  loading,
  error,
}: {
  chapters: Chapter[]
  loading: boolean
  error: boolean
}) {
  return (
    <section aria-labelledby="chapters-heading" className="rounded-[14px] border border-border bg-surface">
      <div className="flex items-baseline justify-between gap-3 border-b border-border px-5 py-4">
        <h2 id="chapters-heading" className="font-display text-xl text-fg">
          章节目录
        </h2>
        <span className="font-mono text-[10px] text-muted">{chapters.length} 章</span>
      </div>
      {loading ? (
        <div role="status" className="space-y-3 p-5" aria-label="正在加载章节目录">
          <div className="h-14 animate-pulse rounded-lg bg-fg-soft" />
          <div className="h-14 animate-pulse rounded-lg bg-fg-soft" />
          <span className="sr-only">正在加载章节目录…</span>
        </div>
      ) : error ? (
        <div className="p-5">
          <p className="font-display text-lg text-fg">章节暂不可用</p>
          <p className="mt-1 text-sm text-muted">章节暂时无法加载，请稍后再试。</p>
        </div>
      ) : chapters.length === 0 ? (
        <div className="p-5">
          <p className="font-display text-lg text-fg">还没有可学习的章节</p>
          <p className="mt-1 text-sm text-muted">该书暂无内容，请稍后再来看看。</p>
        </div>
      ) : (
        <ol className="max-h-[430px] divide-y divide-border overflow-y-auto" aria-label="章节列表">
          {chapters.map((chapter) => (
            <li key={chapter.chapter_id} className="flex items-center gap-4 px-5 py-4">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-fg-soft font-mono text-[10px] text-muted">
                {chapter.chapter_order}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[10px] tracking-wide text-muted">
                  第 {chapter.chapter_order} 章
                </p>
                <h3 className="mt-0.5 truncate font-display text-lg text-fg" title={chapter.title}>
                  {chapter.title}
                </h3>
                {chapter.summary ? (
                  <p className="mt-1 truncate text-xs text-muted" title={chapter.summary}>
                    {chapter.summary}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1 text-right">
                <span className="font-mono text-[10px] text-muted">
                  {chapter.estimated_minutes ? `${chapter.estimated_minutes} 分钟` : '时长待定'}
                </span>
                {typeof chapter.is_completed === 'boolean' ? (
                  <span className="text-[11px] text-muted">
                    {chapter.is_completed ? '已完成' : '未完成'}
                  </span>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export function KnowledgePointsSection({ points }: { points: KnowledgePoint[] | null }) {
  if (!points || points.length === 0) return null

  return (
    <section aria-labelledby="knowledge-heading" className="rounded-[14px] border border-border bg-surface p-5">
      <p className="font-mono text-[10px] uppercase tracking-widest text-accent">知识点</p>
      <h2 id="knowledge-heading" className="mt-1 font-display text-2xl text-fg">
        你将学会什么
      </h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {points.map((point) => (
          <article key={point.knowledge_point_id} className="rounded-[10px] bg-fg-soft p-3.5">
            <h3 className="font-display text-lg text-fg">{point.name}</h3>
            {point.description ? (
              <p className="mt-1 text-xs leading-relaxed text-muted">{point.description}</p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  )
}
