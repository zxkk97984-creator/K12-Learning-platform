import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import type { Book, BookProgress } from '@/entities/book/types'
import type { Stage } from '@/entities/student/types'
import { useCompanionStore, useTeacherName } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import type { Recommendation } from '@/shared/api/recommendation-service'
import { useConversationStore } from '@/features/conversation'
import { useScreenContext } from '@/features/screen-context'
import { contentService, recommendationService } from '@/shared/services'

const TOPICS = ['AI 基础', '机器人', '编程', '数据', 'AI 伦理', '数字素养']
const STAGE_LABEL: Record<Stage, string> = {
  PRIMARY: '小学',
  JUNIOR: '初中',
  SENIOR: '高中',
}

function bookStage(book: Book): Stage {
  if (book.grade_max <= 6) return 'PRIMARY'
  if (book.grade_min >= 10) return 'SENIOR'
  return 'JUNIOR'
}

function gradeLabel(book: Book): string {
  return book.grade_min === book.grade_max
    ? `${book.grade_min} 年级`
    : `${book.grade_min}–${book.grade_max} 年级`
}

function progressLabel(progress: BookProgress | undefined): string {
  if (!progress) return '未开始'
  if (progress.status === 'COMPLETED') return '已完成'
  return progress.chapter_id ? '继续' : '已开始'
}

function BookCover({ book }: { book: Book }) {
  if (book.cover_url) {
    return (
      <img
        src={book.cover_url}
        alt={`《${book.title}》封面`}
        loading="lazy"
        className="h-40 w-full object-contain"
      />
    )
  }
  return (
    <div className="flex h-40 w-full items-center justify-center bg-fg-soft">
      <span className="px-4 text-center font-display text-lg leading-snug text-fg">{book.title}</span>
    </div>
  )
}

export default function LibraryPage() {
  const navigate = useNavigate()
  const runIntent = useConversationStore((state) => state.runIntent)
  const { screenContext } = useScreenContext()
  const teacherName = useTeacherName()

  const [books, setBooks] = useState<Book[]>([])
  const [progressByBook, setProgressByBook] = useState<Record<string, BookProgress>>({})
  const [grade, setGrade] = useState<'推荐' | Stage>('推荐')
  const [topics, setTopics] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [moreFilters, setMoreFilters] = useState(false)

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [errorMessage, setErrorMessage] = useState('')
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [total, setTotal] = useState<number | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [recLoading, setRecLoading] = useState(true)
  const [recError, setRecError] = useState(false)

  // URL 同步：搜索/年级/主题写入 URL，返回书库时保持。
  useEffect(() => {
    const url = new URL(window.location.href)
    const param = url.searchParams
    const s = param.get('search')
    const g = param.get('grade')
    const t = param.get('topic')
    if (s) setSearch(s)
    if (g && ['推荐', 'PRIMARY', 'JUNIOR', 'SENIOR'].includes(g)) setGrade(g as '推荐' | Stage)
    else setGrade('推荐')
    if (t) setTopics(t.split(',').filter(Boolean))
  }, [])

  const syncUrl = useCallback((nextSearch: string, nextGrade: '推荐' | Stage, nextTopics: string[]) => {
    const url = new URL(window.location.href)
    if (nextSearch) url.searchParams.set('search', nextSearch)
    else url.searchParams.delete('search')
    if (nextGrade !== '推荐') url.searchParams.set('grade', nextGrade)
    else url.searchParams.delete('grade')
    if (nextTopics.length) url.searchParams.set('topic', nextTopics.join(','))
    else url.searchParams.delete('topic')
    window.history.replaceState(null, '', url.toString())
  }, [])

  const loadRecommendations = useCallback(async () => {
    setRecLoading(true)
    setRecError(false)
    try {
      setRecommendations(await recommendationService.getRecommendations())
    } catch {
      setRecommendations([])
      setRecError(true)
    } finally {
      setRecLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRecommendations()
  }, [loadRecommendations])

  const dismissRecommendation = useCallback(
    async (recommendationId: string) => {
      try {
        await recommendationService.dismissRecommendation(recommendationId)
      } catch {
        // 静默忽略，刷新时自然重试
      }
      await loadRecommendations()
    },
    [loadRecommendations],
  )

  const loadPage = useCallback(
    async (params: { cursor?: string; append?: boolean }) => {
      const { cursor, append } = params
      if (append) setLoadingMore(true)
      else setStatus('loading')
      try {
        const page = await contentService.getBooksPage({
          search: search.trim() || undefined,
          stage: grade === '推荐' ? undefined : grade,
          topic: topics[0],
          cursor,
          limit: 12,
        })
        const items = page.items
        setBooks((current) => (append ? [...current, ...items] : items))
        setNextCursor(page.meta.next_cursor ?? null)
        setHasMore(Boolean(page.meta.has_more))
        setTotal(typeof page.meta.total === 'number' ? page.meta.total : null)
        setStatus('success')
        setErrorMessage('')
      } catch (error) {
        if (!append) {
          setStatus('error')
          setErrorMessage(error instanceof Error ? error.message : '暂时无法加载书库')
        }
      } finally {
        if (append) setLoadingMore(false)
      }
    },
    [search, grade, topics],
  )

  // 筛选/搜索变化：重置列表与游标（搜索防抖 300ms）。
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      void loadPage({})
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [loadPage])

  // 进度独立加载；失败不影响书列表。
  useEffect(() => {
    void (async () => {
      try {
        const progress = await contentService.getProgress()
        setProgressByBook(Object.fromEntries(progress.map((item) => [item.book_id, item])))
      } catch {
        setProgressByBook({})
      }
    })()
  }, [books])

  const featuredRecommendations = recommendations
    .map((recommendation) => ({
      recommendation,
      book: books.find((item) => item.book_id === recommendation.related_book_id),
    }))
    .filter((entry): entry is { recommendation: Recommendation; book: Book } => Boolean(entry.book))
    .slice(0, 3)

  const showFeatured = grade === '推荐' && topics.length === 0 && !search.trim()

  const triggerIntent = (intent: ConversationIntent) => {
    runIntent(intent, undefined, screenContext)
    useCompanionStore.getState().setOpen(true)
  }

  const openBook = (bookId: string) => navigate(`/books/${bookId}`)

  const clearFilters = () => {
    setGrade('推荐')
    setTopics([])
    setSearch('')
    syncUrl('', '推荐', [])
  }

  const chooseGrade = (option: '推荐' | Stage) => {
    setGrade(option)
    syncUrl(search, option, topics)
  }

  const toggleTopic = (topic: string) => {
    const next = topics.includes(topic) ? topics.filter((item) => item !== topic) : [topic]
    setTopics(next)
    syncUrl(search, grade, next)
  }

  const onSearch = (value: string) => {
    setSearch(value)
    if (grade === '推荐' && topics.length === 0) syncUrl(value, grade, topics)
  }

  const knownTotal = total ?? books.length
  const shownLabel = total != null ? `已显示 ${books.length} / 共 ${total} 本` : `已显示 ${books.length} 本`

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">学习 · 书库</p>
      <h1 className="mt-3 font-display text-3xl leading-tight text-fg">
        找到下一本适合你的书。
      </h1>
      <p className="mt-3 max-w-[52ch] text-base leading-relaxed text-muted">
        内容按年级和兴趣整理。{teacherName}会把你的最近学习变化，也放进推荐理由里。
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <label className="sr-only" htmlFor="library-search">搜索书库</label>
        <input
          id="library-search"
          type="search"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="搜索书名、知识点或主题"
          aria-label="搜索书库"
          className="h-11 min-w-[220px] flex-1 rounded-[12px] border border-border bg-surface px-3 text-base text-fg outline-none focus-visible:border-accent"
        />
        <div className="flex gap-0.5 rounded-[12px] bg-fg-soft p-1">
          {(['推荐', 'PRIMARY', 'JUNIOR', 'SENIOR'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={grade === option}
              onClick={() => chooseGrade(option)}
              className={`rounded-lg px-3.5 py-2 text-sm ${
                grade === option ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
              }`}
            >
              {option === '推荐' ? '推荐' : STAGE_LABEL[option]}
            </button>
          ))}
        </div>
        <button
          type="button"
          aria-expanded={moreFilters}
          className="rounded-[12px] px-3 py-2 text-sm text-muted hover:bg-fg-soft hover:text-fg"
          onClick={() => setMoreFilters((current) => !current)}
        >
          {moreFilters ? '收起筛选 ▴' : '更多筛选 ▾'}
        </button>
      </div>

      {moreFilters ? (
        <div className="mt-3 flex items-center gap-2.5">
          <span className="text-sm text-muted">主题</span>
          <div className="flex gap-1.5 overflow-x-auto">
            {TOPICS.map((topic) => {
              const active = topics.includes(topic)
              return (
                <button
                  key={topic}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleTopic(topic)}
                  className={`rounded-full border px-3 py-2 text-sm whitespace-nowrap ${
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
            <span className="text-xs text-muted">基于你的真实学习数据</span>
          </div>
          {recLoading ? (
            <p className="mt-4 text-sm text-muted">正在根据你的学习数据生成精选…</p>
          ) : recError ? (
            <div className="mt-4 rounded-[12px] border border-border p-4">
              <p className="text-sm text-fg">推荐服务暂时不可用</p>
              <button
                type="button"
                className="mt-2 rounded-[10px] border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-fg"
                onClick={() => void loadRecommendations()}
              >
                重试
              </button>
            </div>
          ) : featuredRecommendations.length === 0 ? (
            <p className="mt-4 text-sm text-muted">
              还没有可推荐的书籍——先去阅读一章，精选会基于你的真实进度出现。
            </p>
          ) : null}
          <div className="mt-4 grid grid-cols-3 gap-4 max-md:grid-cols-1">
            {featuredRecommendations.map(({ book, recommendation }) => {
              const progress = progressByBook[book.book_id]
              return (
                <article key={book.book_id} className="overflow-hidden rounded-[14px] border border-border bg-surface">
                  <BookCover book={book} />
                  <div className="p-4">
                    <span className="text-xs text-muted">
                      {bookStage(book) === 'PRIMARY' ? '小学' : bookStage(book) === 'SENIOR' ? '高中' : '初中'} · {book.tags[0]}
                    </span>
                    <h3 className="mt-1.5 font-display text-lg leading-tight text-fg">
                      <button
                        type="button"
                        className="w-full cursor-pointer text-left font-display text-lg leading-tight text-fg hover:text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                        onClick={() => openBook(book.book_id)}
                      >
                        {book.title}
                      </button>
                    </h3>
                    <p className="mt-1 text-sm text-muted">{gradeLabel(book)} · {book.chapter_count} 章 · 预计 {book.estimated_minutes} 分钟</p>
                    <div className="mt-2 flex min-h-[30px] items-center justify-between border-t border-border pt-2">
                      <span className="text-sm text-muted">{progressLabel(progress)}</span>
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          className="text-sm text-muted hover:text-fg hover:underline"
                          onClick={() => openBook(book.book_id)}
                        >
                          详情
                        </button>
                        {progress?.chapter_id ? (
                          <button
                            type="button"
                            className="text-sm text-fg hover:text-accent"
                            onClick={() => navigate(`/learn/${book.book_id}/${progress.chapter_id}`)}
                          >
                            继续 →
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {recommendation.reason ? (
                      <p className="mt-2 border-t border-border pt-2 text-sm leading-relaxed text-muted">
                        {recommendation.reason}
                      </p>
                    ) : null}
                    <div className="mt-1.5 flex items-center gap-3">
                      {recommendation.recommendation_id ? (
                        <button
                          type="button"
                          data-testid={`dismiss-${recommendation.recommendation_id}`}
                          className="text-sm text-muted hover:text-fg hover:underline"
                          onClick={() => void dismissRecommendation(recommendation.recommendation_id)}
                        >
                          不感兴趣
                        </button>
                      ) : null}
                      {recommendation.evidence_ids.length > 0 ? (
                        <button
                          type="button"
                          className="text-sm text-muted hover:text-fg hover:underline"
                          onClick={() => triggerIntent('recommend-next' as ConversationIntent)}
                        >
                          为什么推荐？
                        </button>
                      ) : null}
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        </>
      ) : null}

      <div className="mt-6 flex items-baseline justify-between border-b border-fg pb-2.5">
        <h2 className="font-display text-xl text-fg">全部书籍</h2>
        <span className="text-xs text-muted">{status === 'success' ? shownLabel : ''}</span>
      </div>

      {status === 'loading' ? (
        <div className="mt-4 rounded-[12px] border border-border p-8 text-center text-sm text-muted">
          正在加载书库…
        </div>
      ) : status === 'error' ? (
        <div className="mt-4 rounded-[12px] border border-border p-8 text-center">
          <h3 className="font-display text-xl text-fg">暂时无法加载书库</h3>
          <p className="mt-2 text-sm text-muted">{errorMessage || '请稍后重试。'}</p>
          <button
            type="button"
            className="mt-4 rounded-[10px] border border-border bg-surface px-3.5 py-2 text-sm text-fg hover:border-fg"
            onClick={() => void loadPage({})}
          >
            重试
          </button>
        </div>
      ) : books.length === 0 ? (
        <div className="mt-4 rounded-[12px] border border-dashed border-border p-8 text-center">
          <h3 className="font-display text-xl text-fg">没有找到匹配的书</h3>
          <p className="mt-2 text-sm text-muted">换一个关键词，或者清除筛选再试试。</p>
          <button
            type="button"
            className="mt-4 rounded-[10px] border border-border bg-surface px-3.5 py-2 text-sm text-fg hover:border-fg"
            onClick={clearFilters}
          >
            清除筛选
          </button>
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-3 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
            {books.map((book) => {
              const progress = progressByBook[book.book_id]
              return (
                <article key={book.book_id} className="overflow-hidden rounded-[14px] border border-border bg-surface">
                  <BookCover book={book} />
                  <div className="p-4">
                    <span className="text-xs text-muted">
                      {bookStage(book) === 'PRIMARY' ? '小学' : bookStage(book) === 'SENIOR' ? '高中' : '初中'} · {book.tags[0]}
                    </span>
                    <h3 className="mt-1.5 font-display text-lg leading-tight text-fg">
                      <button
                        type="button"
                        className="w-full cursor-pointer text-left font-display text-lg leading-tight text-fg hover:text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                        onClick={() => openBook(book.book_id)}
                      >
                        {book.title}
                      </button>
                    </h3>
                    <p className="mt-1 text-sm text-muted">{gradeLabel(book)} · {book.chapter_count} 章 · 预计 {book.estimated_minutes} 分钟</p>
                    <div className="mt-2 flex min-h-[30px] items-center justify-between border-t border-border pt-2">
                      <span className="text-sm text-muted">{progressLabel(progress)}</span>
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          className="text-sm text-muted hover:text-fg hover:underline"
                          onClick={() => openBook(book.book_id)}
                        >
                          详情
                        </button>
                        {progress?.chapter_id ? (
                          <button
                            type="button"
                            className="text-sm text-fg hover:text-accent"
                            onClick={() => navigate(`/learn/${book.book_id}/${progress.chapter_id}`)}
                          >
                            继续 →
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
          {hasMore ? (
            <div className="mt-5 text-center">
              <button
                type="button"
                disabled={loadingMore}
                className="rounded-[12px] border border-border bg-surface px-4 py-2.5 text-sm text-fg hover:border-fg disabled:opacity-60"
                onClick={() => void loadPage({ cursor: nextCursor ?? undefined, append: true })}
              >
                {loadingMore ? '加载中…' : `加载更多（已显示 ${books.length} 本${total != null ? ` / ${total}` : ''}）`}
              </button>
            </div>
          ) : null}
          {knownTotal > 0 && !hasMore ? (
            <p className="mt-4 text-center text-xs text-muted">{shownLabel}</p>
          ) : null}
        </>
      )}
    </section>
  )
}
