import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import type { Book, BookProgress, Chapter, KnowledgePoint } from '@/entities/book/types'
import { contentService } from '@/shared/services'

import {
  BookCover,
  ChaptersSection,
  KnowledgePointsSection,
  ProgressPanel,
} from './BookDetailSections'

function gradeLabel(book: Book): string {
  if (book.grade_max <= 6) return '小学'
  if (book.grade_min >= 10) return '高中'
  return '初中'
}

function sortChapters(chapters: Chapter[]): Chapter[] {
  return [...chapters].sort((a, b) => a.chapter_order - b.chapter_order)
}

export default function BookDetailPage() {
  const { bookId = '' } = useParams<{ bookId: string }>()
  const navigate = useNavigate()
  const [retryKey, setRetryKey] = useState(0)
  const [book, setBook] = useState<Book | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [progress, setProgress] = useState<BookProgress | null>(null)
  const [knowledgePoints, setKnowledgePoints] = useState<KnowledgePoint[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [chaptersLoading, setChaptersLoading] = useState(true)
  const [bookError, setBookError] = useState(false)
  const [chaptersError, setChaptersError] = useState(false)
  const [progressUnavailable, setProgressUnavailable] = useState(false)

  useEffect(() => {
    let cancelled = false

    setLoading(true)
    setChaptersLoading(true)
    setBook(null)
    setChapters([])
    setProgress(null)
    setKnowledgePoints(null)
    setBookError(false)
    setChaptersError(false)
    setProgressUnavailable(false)

    const load = async () => {
      const [bookResult, chaptersResult, progressResult] = await Promise.allSettled([
        contentService.getBook(bookId),
        contentService.getChapters(bookId),
        contentService.getBookProgress(bookId),
      ])

      if (cancelled) return

      const fetchedBook = bookResult.status === 'fulfilled' ? bookResult.value : null
      const fetchedChapters =
        chaptersResult.status === 'fulfilled' ? sortChapters(chaptersResult.value) : []
      const fetchedProgress = progressResult.status === 'fulfilled' ? progressResult.value : null

      setBook(fetchedBook)
      setBookError(bookResult.status === 'rejected')
      setChapters(fetchedChapters)
      setChaptersError(chaptersResult.status === 'rejected')
      setChaptersLoading(false)
      setProgress(fetchedProgress)
      setProgressUnavailable(progressResult.status === 'rejected')
      setLoading(false)

      if (!fetchedBook || fetchedChapters.length === 0) return

      const knowledgeChapterId =
        fetchedProgress?.chapter_id &&
        fetchedChapters.some((chapter) => chapter.chapter_id === fetchedProgress.chapter_id)
          ? fetchedProgress.chapter_id
          : fetchedChapters[0].chapter_id

      try {
        const detail = await contentService.getChapter(knowledgeChapterId)
        if (!cancelled) setKnowledgePoints(detail.knowledge_points)
      } catch {
        if (!cancelled) setKnowledgePoints(null)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [bookId, retryKey])

  if (loading) {
    return (
      <section className="py-8" aria-busy="true">
        <Link to="/library" className="text-sm text-muted hover:text-fg">
          ← 返回书库
        </Link>
        <div role="status" className="mt-12 rounded-[14px] border border-border bg-surface p-8">
          <p className="font-display text-2xl text-fg">正在打开这本书…</p>
          <p className="mt-2 text-sm text-muted">正在读取书本信息和章节目录。</p>
        </div>
      </section>
    )
  }

  if (bookError || !book) {
    return (
      <section className="py-8">
        <Link to="/library" className="text-sm text-muted hover:text-fg">
          ← 返回书库
        </Link>
        <div role="alert" className="mt-12 rounded-[14px] border border-dashed border-border bg-surface p-8">
          <p className="font-display text-2xl text-fg">这本书暂时打不开</p>
          <p className="mt-2 text-sm text-muted">书本信息加载失败，请稍后重试。</p>
          <button
            type="button"
            className="mt-5 min-h-[44px] rounded-[10px] border border-border bg-surface px-4 py-2 text-sm text-fg hover:border-fg"
            onClick={() => setRetryKey((current) => current + 1)}
          >
            重新加载
          </button>
        </div>
      </section>
    )
  }

  const activeChapter = progress?.chapter_id
    ? chapters.find((chapter) => chapter.chapter_id === progress.chapter_id)
    : undefined
  const targetChapterId = progress?.chapter_id ?? chapters[0]?.chapter_id
  const canStartLearning = !chaptersLoading && !chaptersError && Boolean(targetChapterId)
  const actionLabel = progress?.chapter_id ? '继续学习' : '开始学习'

  const startLearning = () => {
    if (!canStartLearning || !targetChapterId) return
    navigate(`/learn/${bookId}/${targetChapterId}`)
  }

  return (
    <section className="py-8 pb-16">
      <div className="flex items-center justify-between gap-4">
        <Link to="/library" className="text-sm text-muted hover:text-fg">
          ← 返回书库
        </Link>
        <span className="font-mono text-[10px] uppercase tracking-widest text-accent">书库 · 书本详情</span>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
        <BookCover book={book} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="rounded-full bg-fg-soft px-2.5 py-1">{gradeLabel(book)}</span>
            <span>{book.grade_min}—{book.grade_max} 年级</span>
            {book.tags[0] ? <span>· {book.tags[0]}</span> : null}
          </div>
          <h1 className="mt-4 font-display text-5xl leading-[1.05] text-fg max-md:text-4xl">
            {book.title}
          </h1>
          <p className="mt-4 max-w-[60ch] text-base leading-relaxed text-muted">
            {book.description || '这本书还没有简介。'}
          </p>
          <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-muted">
            <span>预计 {book.estimated_minutes} 分钟</span>
            <span>{book.chapter_count || chapters.length} 章</span>
            {book.author ? <span>作者：{book.author}</span> : null}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={!canStartLearning}
              className="min-h-[44px] rounded-[10px] bg-fg px-5 py-2.5 text-sm text-surface transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45"
              onClick={startLearning}
            >
              {canStartLearning ? actionLabel : '暂无内容'}
            </button>
            {!canStartLearning ? (
              <span className="text-xs text-muted">
                {chaptersError ? '章节目录不可用，请稍后再试。' : '该书暂无可学习内容。'}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.72fr)]">
        <ChaptersSection chapters={chapters} loading={chaptersLoading} error={chaptersError} />
        <ProgressPanel
          progress={progress}
          chapterTitle={activeChapter?.title ?? (progress?.chapter_id ? '当前章节' : undefined)}
          unavailable={progressUnavailable}
        />
      </div>

      <div className="mt-5">
        <KnowledgePointsSection points={knowledgePoints} />
      </div>
    </section>
  )
}
