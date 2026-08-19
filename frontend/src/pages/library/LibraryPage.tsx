import { useEffect, useMemo, useState } from 'react'

import type { Book } from '@/entities/book/types'
import type { Stage } from '@/entities/student/types'
import { useCompanionStore } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import { useConversationStore } from '@/features/conversation'
import { bookRecommendations } from '@/mocks/data/recommendations'
import { contentService } from '@/mocks/services'

const TOPICS = ['AI 基础', '机器人', '编程', '数据', 'AI 伦理', '数字素养']
const TINT_BG: Record<number, string> = {
  1: 'oklch(80% 0.07 250)',
  2: 'oklch(80% 0.07 160)',
  3: 'oklch(81% 0.06 55)',
  4: 'oklch(80% 0.07 330)',
}

function bookStage(book: Book): Stage {
  if (book.grade_max <= 6) return 'PRIMARY'
  if (book.grade_min >= 10) return 'SENIOR'
  return 'JUNIOR'
}

export default function LibraryPage() {
  const runIntent = useConversationStore((state) => state.runIntent)
  const [books, setBooks] = useState<Book[]>([])
  const [grade, setGrade] = useState<'推荐' | Stage>('推荐')
  const [topics, setTopics] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [moreFilters, setMoreFilters] = useState(false)

  useEffect(() => {
    void (async () => {
      setBooks(await contentService.getBooks())
    })()
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return books.filter((book) => {
      const matchesGrade = grade === '推荐' || bookStage(book) === grade
      const matchesTopic = topics.length === 0 || topics.includes(book.tags[0] ?? '')
      const matchesSearch =
        !needle || `${book.title} ${book.keywords} ${book.tags.join(' ')}`.toLowerCase().includes(needle)
      return matchesGrade && matchesTopic && matchesSearch
    })
  }, [books, grade, topics, search])

  const showFeatured = grade === '推荐' && topics.length === 0 && !search.trim()
  const featuredBooks = books.slice(0, 3)

  const triggerIntent = (intent: ConversationIntent) => {
    runIntent(intent)
    useCompanionStore.getState().setOpen(true)
  }

  const clearFilters = () => {
    setGrade('推荐')
    setTopics([])
    setSearch('')
  }

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">学习 · 书库</p>
      <h1 className="mt-3 max-w-[16ch] font-display text-5xl leading-none text-fg">
        找到下一本适合你的书。
      </h1>
      <p className="mt-3 max-w-[52ch] text-sm leading-relaxed text-muted">
        内容按年级和兴趣整理。霜铃会把你的最近学习变化，也放进推荐理由里。
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索书名、知识点或主题"
          aria-label="搜索书库"
          className="h-[42px] min-w-[220px] flex-1 rounded-[10px] border border-border bg-surface px-3 text-[13px] text-fg outline-none focus:border-accent"
        />
        <div className="flex gap-0.5 rounded-[10px] bg-fg-soft p-1">
          {(['推荐', 'PRIMARY', 'JUNIOR', 'SENIOR'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={grade === option}
              onClick={() => setGrade(option)}
              className={`rounded-lg px-3.5 py-1.5 text-xs ${
                grade === option ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
              }`}
            >
              {option === '推荐' ? '推荐' : option === 'PRIMARY' ? '小学' : option === 'JUNIOR' ? '初中' : '高中'}
            </button>
          ))}
        </div>
        <button
          type="button"
          aria-expanded={moreFilters}
          className="rounded-[10px] px-2.5 py-1.5 text-xs text-muted hover:bg-fg-soft hover:text-fg"
          onClick={() => setMoreFilters((current) => !current)}
        >
          {moreFilters ? '收起筛选 ▴' : '更多筛选 ▾'}
        </button>
      </div>

      {moreFilters ? (
        <div className="mt-3 flex items-center gap-2.5">
          <span className="font-mono text-[10px] text-muted">主题</span>
          <div className="flex gap-1.5 overflow-x-auto">
            {TOPICS.map((topic) => {
              const active = topics.includes(topic)
              return (
                <button
                  key={topic}
                  type="button"
                  aria-pressed={active}
                  onClick={() =>
                    setTopics((current) =>
                      active ? current.filter((item) => item !== topic) : [...current, topic],
                    )
                  }
                  className={`rounded-full border px-2.5 py-1.5 text-[11px] whitespace-nowrap ${
                    active
                      ? 'border-fg bg-surface text-fg'
                      : 'border-border bg-transparent text-muted hover:border-fg hover:text-fg'
                  }`}
                >
                  {topic}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}

      {showFeatured ? (
        <>
          <div className="mt-6 flex items-baseline justify-between border-b border-fg pb-2.5">
            <h2 className="font-display text-xl text-fg">为你精选</h2>
            <span className="font-mono text-[10px] text-muted">根据最近学习变化</span>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-4 max-md:grid-cols-1">
            {featuredBooks.map((book) => {
              const recommendationIndex = bookRecommendations.findIndex(
                (item) => item.bookId === book.book_id,
              )
              const recommendation = recommendationIndex >= 0 ? bookRecommendations[recommendationIndex] : undefined
              return (
                <article key={book.book_id} className="overflow-hidden rounded-[14px] border border-border bg-surface">
                  <div className="relative min-h-[132px] p-4 text-surface" style={{ backgroundColor: TINT_BG[book.tint ?? 1] ?? 'var(--color-fg)' }}>
                    <span className="font-mono text-xs opacity-60">{book.book_no ?? ''}</span>
                    <strong className="mt-10 block max-w-[12ch] font-display text-xl leading-tight">
                      {book.title}
                    </strong>
                    <span className="mt-1 block font-mono text-[9px] tracking-wide opacity-65">
                      {book.keywords}
                    </span>
                  </div>
                  <div className="p-4">
                    <span className="font-mono text-[10px] text-muted">
                      {book.grade_min <= 6 ? '小学' : book.grade_min <= 9 ? '初中' : '高中'} · {book.tags[0]}
                    </span>
                    <h3 className="mt-1.5 font-display text-lg leading-tight text-fg">{book.title}</h3>
                    <p className="mt-1 text-[11px] text-muted">{book.keywords}</p>
                    <div className="mt-3 flex items-center justify-between border-t border-border pt-2.5">
                      <span className="font-mono text-[9px] text-muted">
                        {book.chapter_count} 章 · 预计 {book.estimated_minutes} 分钟
                      </span>
                    </div>
                    {recommendation ? (
                      <button
                        type="button"
                        className="mt-2 text-[11px] text-muted hover:text-fg hover:underline"
                        onClick={() =>
                          triggerIntent(`book-why-${recommendationIndex + 1}` as ConversationIntent)
                        }
                      >
                        为什么推荐？
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            })}
          </div>
        </>
      ) : null}

      <div className="mt-6 flex items-baseline justify-between border-b border-fg pb-2.5">
        <h2 className="font-display text-xl text-fg">全部书籍</h2>
        <span className="font-mono text-[10px] text-muted">共 {filtered.length} 本</span>
      </div>

      {filtered.length === 0 ? (
        <div className="mt-4 rounded-[12px] border border-dashed border-border p-8 text-center">
          <h3 className="font-display text-xl text-fg">没有找到匹配的书</h3>
          <p className="mt-2 text-[13px] text-muted">换一个关键词，或者清除筛选再试试。</p>
          <button
            type="button"
            className="mt-4 rounded-[10px] border border-border bg-surface px-3.5 py-2 text-xs text-fg hover:border-fg"
            onClick={clearFilters}
          >
            清除筛选
          </button>
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-md:grid-cols-2 max-sm:grid-cols-1">
          {filtered.map((book) => {
            const recommendationIndex = bookRecommendations.findIndex(
              (item) => item.bookId === book.book_id,
            )
            const recommendation = recommendationIndex >= 0 ? bookRecommendations[recommendationIndex] : undefined
            return (
              <article key={book.book_id} className="overflow-hidden rounded-[12px] border border-border bg-surface">
                <div className="relative h-[54px] border-b border-border" style={{ backgroundColor: TINT_BG[book.tint ?? 1] ?? 'var(--color-fg)' }}>
                  <span className="absolute top-2.5 left-3.5 font-display text-xl text-fg/20">{book.book_no ?? ''}</span>
                </div>
                <div className="p-3.5">
                  <span className="font-mono text-[9px] text-muted">
                    {book.grade_min <= 6 ? '小学' : book.grade_min <= 9 ? '初中' : '高中'} · {book.tags[0]}
                  </span>
                  <h3 className="mt-1.5 font-display text-lg leading-tight text-fg">{book.title}</h3>
                  <p className="mt-1 text-[11px] text-muted">{book.keywords}</p>
                  <div className="mt-2.5 font-mono text-[9px] text-muted">
                    {book.chapter_count} 章 · 预计 {book.estimated_minutes} 分钟
                  </div>
                  <div className="mt-2 flex min-h-[30px] items-center justify-between border-t border-border pt-2">
                    <span className="text-[11px] text-muted">未开始</span>
                  </div>
                  {recommendation ? (
                    <button
                      type="button"
                      className="mt-1 text-[11px] text-muted hover:text-fg hover:underline"
                      onClick={() =>
                        triggerIntent(`book-why-${recommendationIndex + 1}` as ConversationIntent)
                      }
                    >
                      为什么推荐？
                    </button>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
