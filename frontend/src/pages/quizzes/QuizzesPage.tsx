import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import type { QuizSession } from '@/entities/quiz/types'
import { quizSource } from '@/features/quiz/lib'
import { quizService } from '@/mocks/services'

type QuizFilter = '全部' | '章节测验' | 'AI 小测' | '更早'

const FILTERS: QuizFilter[] = ['全部', '章节测验', 'AI 小测', '更早']

export default function QuizzesPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<QuizSession[]>([])
  const [sources, setSources] = useState<Record<string, { bookTitle: string; chapterTitle: string }>>({})
  const [filter, setFilter] = useState<QuizFilter>('全部')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const list = await quizService.getQuizSessions()
        if (cancelled) return
        setSessions(list)
        const entries = await Promise.all(
          list.map(async (session) => [
            session.quiz_session_id,
            await quizSource(session.book_id, session.chapter_id),
          ]),
        )
        if (!cancelled) setSources(Object.fromEntries(entries))
      } catch {
        if (!cancelled) setSessions([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const filtered =
    filter === '全部'
      ? sessions
      : filter === '更早'
        ? []
        : sessions.filter((session) => session.quiz_kind === (filter === '章节测验' ? 'CHAPTER_QUIZ' : 'AI_QUIZ'))

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">测验 · 历史记录</p>
      <h1 className="mt-3 font-display text-4xl text-fg">每一次答题，都会留下线索。</h1>

      <div className="mt-6 flex items-center justify-between gap-3">
        <div className="flex gap-1.5 overflow-x-auto">
          {FILTERS.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={filter === item}
              onClick={() => setFilter(item)}
              className={`rounded-full border px-3 py-1.5 text-[11px] whitespace-nowrap ${
                filter === item
                  ? 'border-fg bg-surface text-fg'
                  : 'border-border bg-transparent text-muted hover:border-fg hover:text-fg'
              }`}
            >
              {item}
            </button>
          ))}
        </div>
        <span className="font-mono text-[10px] text-muted">共 {filtered.length} 次测验</span>
      </div>

      <div className="mt-5 border-t border-fg">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted">正在加载测验记录…</p>
        ) : filtered.length === 0 ? (
          <div className="mt-4 rounded-[12px] border border-dashed border-border p-8 text-center">
            <h3 className="font-display text-xl text-fg">
              {filter === '更早' ? '更早的测验' : '这里还没有这类测验'}
            </h3>
            <p className="mt-2 text-[13px] text-muted">换一个筛选条件，或者让霜铃现场出一份。</p>
          </div>
        ) : (
          filtered.map((session) => {
            const source = sources[session.quiz_session_id]
            const summary = session.result_summary
            return (
              <article key={session.quiz_session_id} className="grid grid-cols-[84px_minmax(0,1fr)] gap-5 border-b border-border py-5 max-md:grid-cols-[56px_minmax(0,1fr)]">
                <time className="font-mono text-[10px] text-muted">{session.created_at.slice(5, 10)}</time>
                <div>
                  <div className="flex flex-wrap items-baseline gap-2.5">
                    <span className="font-mono text-[9px] tracking-wider text-muted">
                      {session.quiz_kind === 'CHAPTER_QUIZ' ? '章节测验' : 'AI 小测'}
                    </span>
                    <strong className="font-display text-xl text-fg">{session.title}</strong>
                    <span className="ml-auto font-mono text-xs text-fg">
                      {summary ? `${summary.correct} / ${summary.total}` : '—'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    《{source?.bookTitle ?? '—'}》 · {source?.chapterTitle ?? '—'}
                  </p>
                  {session.ai_feedback ? (
                    <blockquote className="mt-2 border-l-2 border-fg pl-3 font-display text-sm leading-relaxed text-fg">
                      {session.ai_feedback}
                    </blockquote>
                  ) : null}
                  <div className="mt-3">
                    <button
                      type="button"
                      className="rounded-[10px] border border-border bg-surface px-3 py-1.5 text-xs text-fg hover:border-fg"
                      onClick={() => navigate(`/quizzes/${session.quiz_session_id}`)}
                    >
                      查看答卷
                    </button>
                  </div>
                </div>
              </article>
            )
          })
        )}
      </div>
    </section>
  )
}
