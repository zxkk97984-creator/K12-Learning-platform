import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import type { Chapter, ChapterDetail } from '@/entities/book/types'
import { useCompanionStore, useTeacherName } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import { useConversationStore } from '@/features/conversation'
import { useScreenContext } from '@/features/screen-context'
import { contentService } from '@/shared/services'
import { learningService } from '@/shared/api/learning-service'
import { ChapterCompletionCard } from './ChapterCompletionCard'
import {
  sectionEventKey,
  setCurrentLearningSessionId,
  shouldEmitSectionRead,
  type EventLinkage,
} from '@/features/learning/events'

interface PopoverState {
  text: string
  left: number
  top: number
}

interface SessionLifecycle {
  key: string
  sessionId: string | null
  ended: boolean
  cleanupTimer: number | null
}

function shouldTrackBookStarted(bookId: string): boolean {
  try {
    const key = `shuangling-book-started:${bookId}`
    if (window.sessionStorage.getItem(key)) return false
    window.sessionStorage.setItem(key, '1')
  } catch {
    // 埋点状态不可用时仍尝试发送一次，不影响阅读。
  }
  return true
}

import { ContentBlockView } from './ContentBlockView'

export default function ReaderPage() {
  // Phase 5-B-I：路由必须提供真实 UUID；不再默认 b1/ch3 演示入口
  const params = useParams()
  const bookId = params.bookId ?? ''
  const chapterId = params.chapterId ?? ''
  // Phase 5-B-I：缺任一路由参数 → 渲染明确错误页（不访问演示数据）
  const routeMissing = !bookId || !chapterId
  const navigate = useNavigate()
  const { setScreenContext, screenContext } = useScreenContext()
  const runIntent = useConversationStore((state) => state.runIntent)
  const ensureConversationId = useConversationStore((state) => state.ensureConversationId)
  const teacherName = useTeacherName()

  const [bookTitle, setBookTitle] = useState('书本')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [detail, setDetail] = useState<ChapterDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [popover, setPopover] = useState<PopoverState | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const sessionRef = useRef<SessionLifecycle | null>(null)
  const visibleBlockIdRef = useRef<string | null>(null)
  const lastSectionReadRef = useRef<{ chapterId: string | null; section: string | null }>({
    chapterId: null,
    section: null,
  })
  const progressReadyRef = useRef(false)
  const skipInitialProgressRef = useRef(false)
  const lastProgressRef = useRef<{ blockId: string | null; sentAt: number } | null>(null)
  const lastSelectedTextRef = useRef('')

  const activeBookId = detail?.book_id ?? bookId
  const activeChapterId = detail?.chapter_id ?? chapterId

  // Phase 3：事件与真实 LearningSession / 内容块 / 知识点全量关联。
  const sessionIdRef = useRef<string | null>(null)
  const emittedKeysRef = useRef<Set<string>>(new Set())

  const trackEvent = useCallback(
    (
      eventType: Parameters<typeof learningService.createEvent>[0]['event_type'],
      payload: Record<string, unknown> = {},
      linkage: EventLinkage = {},
    ) => {
      const blockId =
        linkage.blockId !== undefined ? linkage.blockId : visibleBlockIdRef.current
      void learningService
        .createEvent({
          event_type: eventType,
          occurred_at: new Date().toISOString(),
          book_id: activeBookId,
          chapter_id: activeChapterId,
          ...(sessionIdRef.current ? { session_id: sessionIdRef.current } : {}),
          ...(blockId ? { block_id: blockId } : {}),
          ...(linkage.kpIds && linkage.kpIds.length > 0
            ? { knowledge_point_ids: linkage.kpIds }
            : {}),
          ...(linkage.conversationId
            ? { conversation_id: linkage.conversationId }
            : {}),
          payload,
        })
        .catch(() => undefined)
    },
    [activeBookId, activeChapterId],
  )

  /** 同一 (会话, 事件, 维度) 只发一次；组件卸载不补发，避免重复。 */
  const emitOnce = useCallback(
    (
      key: string,
      eventType: Parameters<typeof trackEvent>[0],
      payload?: Record<string, unknown>,
      linkage?: { blockId?: string | null; kpIds?: string[] },
    ) => {
      const fullKey = `${sessionIdRef.current ?? 'nosession'}:${key}`
      if (emittedKeysRef.current.has(fullKey)) return
      emittedKeysRef.current.add(fullKey)
      trackEvent(eventType, payload, linkage)
    },
    [trackEvent],
  )

  const persistProgress = useCallback(
    (blockId: string | null, force = false) => {
      if (!detail || !progressReadyRef.current) return
      if (skipInitialProgressRef.current) {
        skipInitialProgressRef.current = false
        return
      }
      const now = Date.now()
      const last = lastProgressRef.current
      if (!force && last && last.blockId === blockId && now - last.sentAt < 30_000) return
      const blockIndex = detail.content_blocks.findIndex((block) => block.block_id === blockId)
      const positionPercent =
        blockIndex >= 0 && detail.content_blocks.length > 0
          ? Math.round(((blockIndex + 1) / detail.content_blocks.length) * 100)
          : 0
      lastProgressRef.current = { blockId, sentAt: now }
      void learningService
        .upsertProgress(activeBookId, {
          chapter_id: activeChapterId,
          ...(blockId ? { block_id: blockId } : {}),
          status: 'READING',
          position_percent: positionPercent,
        })
        .catch(() => undefined)
    },
    [activeBookId, activeChapterId, detail],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setNotice(null)
    setPopover(null)
    if (routeMissing) {
      setLoading(false)
      return
    }
    void (async () => {
      let chapterList: Chapter[] = []
      try {
        chapterList = await contentService.getChapters(bookId)
      } catch {
        chapterList = []
      }
      let current: ChapterDetail | null = null
      try {
        current = await contentService.getChapter(chapterId)
      } catch {
        const chapter = chapterList.find((item) => item.chapter_id === chapterId)
        if (chapter) current = { ...chapter, content_blocks: [], knowledge_points: [] }
      }
      let title = '书本'
      try {
        title = (await contentService.getBook(bookId)).title
      } catch {
        title = '书本'
      }
      if (cancelled) return
      setBookTitle(title)
      setChapters(chapterList)
      setDetail(current)
      setNotice(current && current.content_blocks.length === 0 ? '本章暂无内容' : null)
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [bookId, chapterId])

  // 进入章节：恢复/创建 BookProgress，并记录章节与书本开始事件。
  useEffect(() => {
    if (!detail || routeMissing) return
    let cancelled = false
    progressReadyRef.current = false
    skipInitialProgressRef.current = false
    lastProgressRef.current = null
    visibleBlockIdRef.current = null
    lastSelectedTextRef.current = ''

    void (async () => {
      let existing = null
      try {
        existing = await contentService.getBookProgress(activeBookId)
      } catch {
        // Learning API 不可用时不阻塞真实内容阅读。
      }
      if (cancelled) return

      const isSameChapter = existing?.chapter_id === activeChapterId
      progressReadyRef.current = true
      skipInitialProgressRef.current = isSameChapter
      lastProgressRef.current = isSameChapter
        ? { blockId: existing?.block_id ?? null, sentAt: Date.now() }
        : null
      void learningService
        .upsertProgress(activeBookId, {
          chapter_id: activeChapterId,
          status: 'READING',
          ...(isSameChapter ? {} : { position_percent: 0 }),
        })
        .catch(() => undefined)
    })()

    emittedKeysRef.current = new Set()
    // 缺口 1a：新章节/新会话必须重置 SECTION_READ 去重基线，
    // 否则新章节同名首小节的事件会被上一章状态吞掉。
    lastSectionReadRef.current = { chapterId: activeChapterId, section: null }

    return () => {
      cancelled = true
    }
  }, [activeBookId, activeChapterId, detail, trackEvent])

  // LearningSession 生命周期：同一章节复用 StrictMode 的短暂 cleanup，真正离开时结算。
  useEffect(() => {
    if (!detail) return
    const key = `${activeBookId}:${activeChapterId}`
    const existing = sessionRef.current
    let lifecycle: SessionLifecycle

    if (existing?.key === key) {
      lifecycle = existing
      lifecycle.ended = false
      if (lifecycle.cleanupTimer !== null) {
        window.clearTimeout(lifecycle.cleanupTimer)
        lifecycle.cleanupTimer = null
      }
    } else {
      lifecycle = { key, sessionId: null, ended: false, cleanupTimer: null }
      sessionRef.current = lifecycle
      void learningService
        .createSession({
          book_id: activeBookId,
          chapter_id: activeChapterId,
          // 后端 entry_route 上限为 64 字符；真实 UUID 路由会超长，保留章节维度即可。
          entry_route: `/reader/${activeChapterId}`,
        })
        .then((session) => {
          lifecycle.sessionId = session.session_id
          sessionIdRef.current = session.session_id
          setCurrentLearningSessionId(session.session_id)
          trackEvent('CHAPTER_STARTED')
          if (shouldTrackBookStarted(activeBookId)) trackEvent('BOOK_STARTED')
          if (lifecycle.ended) {
            const sessionId = lifecycle.sessionId
            lifecycle.sessionId = null
            if (sessionId) void learningService.endSession(sessionId).catch(() => undefined)
          }
        })
        .catch(() => undefined)
    }

    return () => {
      lifecycle.ended = true
      lifecycle.cleanupTimer = window.setTimeout(() => {
        if (!lifecycle.ended) return
        const sessionId = lifecycle.sessionId
        lifecycle.sessionId = null
        lifecycle.cleanupTimer = null
        if (sessionId) void learningService.endSession(sessionId).catch(() => undefined)
        if (sessionRef.current === lifecycle) sessionRef.current = null
        if (sessionIdRef.current === sessionId) sessionIdRef.current = null
        setCurrentLearningSessionId(null)
      }, 0)
    }
  }, [activeBookId, activeChapterId, detail, trackEvent])

  // 定时保存当前阅读位置；章节切换/卸载时由 cleanup 做最后一次写入。
  useEffect(() => {
    const timer = window.setInterval(() => {
      void persistProgress(visibleBlockIdRef.current, true)
    }, 30_000)
    return () => {
      window.clearInterval(timer)
      void persistProgress(visibleBlockIdRef.current, true)
    }
  }, [persistProgress])

  // 写入 ScreenContext（进入 reader 时）
  useEffect(() => {
    if (!detail) return
    setScreenContext({
      route: `/learn/${bookId}/${chapterId}`,
      pageType: 'chapter_reader',
      bookId,
      chapterId,
      chapterTitle: detail.title,
      visibleSection: detail.content_blocks[0]?.section_key ?? undefined,
      contentBlockId: detail.content_blocks[0]?.block_id,
      knowledgePoints: detail.knowledge_points.map((point) => point.slug),
      actions: ['explain', 'summary', 'quiz'],
    })
  }, [detail, bookId, chapterId, setScreenContext])

  // 离开 reader：清空选中文本与可见区块
  useEffect(
    () => () => {
      setScreenContext({ selectedText: undefined, visibleSection: undefined })
    },
    [setScreenContext],
  )

  // IntersectionObserver：最靠上的可见内容块 → visibleSection（rootMargin 对齐原型）
  useEffect(() => {
    const container = contentRef.current
    if (!container || !detail || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
        if (visible) {
          const element = visible.target as HTMLElement
          const blockId = element.closest('[data-block-id]')?.getAttribute('data-block-id') ?? null
          const sectionKey = element.dataset.readSection
          visibleBlockIdRef.current = blockId
          setScreenContext({
            visibleSection: sectionKey,
            contentBlockId: blockId ?? undefined,
          })
          if (
            sectionKey &&
            shouldEmitSectionRead(lastSectionReadRef.current, activeChapterId, sectionKey)
          ) {
            lastSectionReadRef.current = { chapterId: activeChapterId, section: sectionKey }
            emitOnce(
              sectionEventKey(activeChapterId, sectionKey),
              'SECTION_READ',
              { section_key: sectionKey },
            )
          }
          void persistProgress(blockId)
          // 100% 到达末块 → 章节完成一次；末章再触发书籍完成一次
          if (detail && blockId) {
            const index = detail.content_blocks.findIndex((b) => b.block_id === blockId)
            if (index >= 0 && detail.content_blocks.length > 0 && index === detail.content_blocks.length - 1) {
              emitOnce('chapter-finished', 'CHAPTER_FINISHED')
              const isLastChapter =
                chapters.length > 0 &&
                chapters[chapters.length - 1].chapter_id === activeChapterId
              if (isLastChapter) emitOnce('book-finished', 'BOOK_FINISHED')
            }
          }
        }
      },
      { rootMargin: '-18% 0px -55% 0px' },
    )
    container.querySelectorAll('[data-read-section]').forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [activeChapterId, chapters, detail, emitOnce, persistProgress, setScreenContext])

  // 知识卡片可见即产生 KNOWLEDGE_CARD_VIEWED 事件（Phase 3；去重）
  useEffect(() => {
    const container = contentRef.current
    if (!container || !detail || !('IntersectionObserver' in window)) return
    const cards = Array.from(container.querySelectorAll<HTMLElement>('[data-kc-block]'))
    if (cards.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const element = entry.target as HTMLElement
          const blockId = element.dataset.kcBlock ?? null
          const kpIds = (element.dataset.kpIds ?? '')
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean)
          emitOnce(`kc:${blockId}`, 'KNOWLEDGE_CARD_VIEWED', {}, { blockId, kpIds })
          observer.unobserve(element)
        }
      },
      { rootMargin: '0px 0px -20% 0px' },
    )
    cards.forEach((card) => observer.observe(card))
    return () => observer.disconnect()
  }, [detail, emitOnce])

  // 选中文字 → popover（对齐 0-B §2.3，仅 reader 内容区有效）
  useEffect(() => {
    const onSelectionChange = () => {
      const selection = window.getSelection()
      const text = selection?.toString().trim() ?? ''
      const node = selection?.anchorNode?.parentElement
      if (!text || !node || !node.closest('[data-read-container]')) {
        lastSelectedTextRef.current = ''
        setPopover(null)
        return
      }
      const selected = text.slice(0, 50)
      setScreenContext({ selectedText: selected })
      if (lastSelectedTextRef.current !== selected) {
        lastSelectedTextRef.current = selected
        trackEvent('TEXT_SELECTED', { selectedText: selected })
      }
      try {
        const range = selection.getRangeAt(0).getBoundingClientRect()
        setPopover({
          text: selected,
          left: Math.min(Math.max(12, range.left), window.innerWidth - 168),
          top: Math.max(12, range.top - 48),
        })
      } catch {
        setPopover(null)
      }
    }
    document.addEventListener('selectionchange', onSelectionChange)
    return () => document.removeEventListener('selectionchange', onSelectionChange)
  }, [setScreenContext, trackEvent])

  const triggerIntent = async (intent: ConversationIntent) => {
    // 缺口 1b：先确保真实会话存在，事件携带 conversation_id 后再触发对话
    let conversationId: string | null = null
    try {
      conversationId = await ensureConversationId()
    } catch {
      conversationId = null
    }
    if (intent === 'explain') trackEvent('EXPLAIN_REQUESTED', {}, { conversationId })
    if (intent === 'summary') trackEvent('SUMMARY_REQUESTED', {}, { conversationId })
    runIntent(intent, undefined, screenContext)
    useCompanionStore.getState().setOpen(true)
  }

  const askSelected = async () => {
    if (!popover) return
    let conversationId: string | null = null
    try {
      conversationId = await ensureConversationId()
    } catch {
      conversationId = null
    }
    trackEvent(
      'QUESTION_ASKED',
      { selectedText: popover.text, source: 'selection' },
      { blockId: visibleBlockIdRef.current, conversationId },
    )
    runIntent('selected', popover.text, screenContext)
    useCompanionStore.getState().setOpen(true)
    window.getSelection()?.removeAllRanges()
    lastSelectedTextRef.current = ''
    setPopover(null)
  }

  const chapterIndex = chapters.findIndex((chapter) => chapter.chapter_id === activeChapterId)

  // Phase 5-B-I：缺路由参数 → 明确错误页 + 回书库链接（不访问演示数据）
  if (routeMissing) {
    return (
      <section className="grid min-h-[60vh] place-items-center px-6" data-testid="reader-missing-route">
        <div className="text-center">
          <p className="font-mono text-[11px] text-accent">400</p>
          <h1 className="mt-2 font-display text-2xl text-fg">缺少章节参数，无法打开阅读器</h1>
          <p className="mt-2 text-sm text-muted">请从书库选择一本书开始阅读。</p>
          <Link
            to="/library"
            className="mt-5 inline-block rounded-[10px] bg-accent px-4 py-2.5 text-sm text-surface hover:bg-accent/85"
          >
            去书库看看
          </Link>
        </div>
      </section>
    )
  }

  return (
    <div className="py-6">
      <div className="flex min-h-[48px] items-center justify-between border-b border-border">
        <div className="flex items-center gap-2 text-xs text-muted">
          <Link to="/home" className="rounded-[10px] px-2 py-1.5 text-muted hover:text-fg">
            ← 返回首页
          </Link>
          <span>/</span>
          <span>{bookTitle}</span>
          <span>/</span>
          <strong className="text-fg">{detail?.title ?? '…'}</strong>
          <span className="font-mono text-[10px] text-muted">
            第 {chapterIndex >= 0 ? chapterIndex + 1 : '?'} / {chapters.length || '?'} 节
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="rounded-[10px] px-2.5 py-1.5 text-xs text-muted hover:bg-fg-soft hover:text-fg"
            onClick={() => void triggerIntent('summary')}
          >
            总结本页
          </button>
          <button
            type="button"
            className="rounded-[10px] border border-border bg-surface px-2.5 py-1.5 text-xs text-fg hover:border-fg"
            onClick={() => void triggerIntent('quiz')}
          >
            给我出题
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[196px_minmax(0,1fr)_248px] gap-7 pt-8 max-lg:grid-cols-[180px_minmax(0,1fr)] max-md:grid-cols-1">
        <aside className="sticky top-[99px] self-start max-md:static max-md:flex max-md:gap-2 max-md:overflow-x-auto">
          <p className="mb-3 font-mono text-[10px] tracking-wider text-muted max-md:hidden">本章目录</p>
          {chapters.map((chapter) => {
            const active = chapter.chapter_id === activeChapterId
            return (
              <button
                key={chapter.chapter_id}
                type="button"
                aria-current={active ? 'page' : undefined}
                className={`grid w-full grid-cols-[24px_1fr_auto] items-center gap-2 border-t border-border px-1 py-2.5 text-left text-xs ${
                  active ? 'text-fg' : 'text-muted hover:text-fg'
                } max-md:min-w-[150px] max-md:rounded-lg max-md:border max-md:px-2.5`}
                onClick={() => navigate(`/learn/${bookId}/${chapter.chapter_id}`)}
              >
                <span className={`font-mono text-[10px] ${active ? 'text-accent' : ''}`}>
                  {String(chapter.chapter_order).padStart(2, '0')}
                </span>
                <span>{chapter.title}</span>
                {chapter.is_completed ? <span className="text-[10px] text-muted">✓</span> : null}
              </button>
            )
          })}
        </aside>

        <article data-read-container className="max-w-[660px]">
          {loading ? (
            <p className="py-10 text-sm text-muted">正在加载章节…</p>
          ) : detail ? (
            <>
              <p className="font-mono text-[10px] tracking-wider text-accent">
                第 {String(detail.chapter_order).padStart(2, '0')} 章
              </p>
              <h1 className="mt-3 font-display text-4xl leading-[1.18] text-fg">{detail.title}</h1>
              <div ref={contentRef} className="mt-8">
                {detail.content_blocks.map((block) => (
                  <div key={block.block_id} data-block-id={block.block_id}>
                    <ContentBlockView block={block} onExplain={() => void triggerIntent('explain')} />
                  </div>
                ))}
                {notice ? (
                  <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted">
                    {notice}
                  </p>
                ) : null}
                <div className="mt-8">
                  <ChapterCompletionCard
                    chapters={chapters}
                    chapterId={activeChapterId}
                    chapterTitle={detail?.title ?? ''}
                    alreadyCompleted={detail?.is_completed ?? false}
                    onSubmit={() => learningService.markChapterCompleted(activeChapterId)}
                    onNavigateNext={(nextChapterId) =>
                      navigate(`/learn/${activeBookId}/${nextChapterId}`)
                    }
                    onPractice={() => void triggerIntent('quiz')}
                  />
                </div>
                <div className="mt-4 flex items-center justify-between border-t border-fg pt-4">
                  <span className="text-xs text-muted">选择一段文字，直接问{teacherName}。</span>
                  <button
                    type="button"
                    className="rounded-[10px] bg-accent px-3 py-2 text-xs text-surface hover:bg-accent/85"
                    onClick={() => void triggerIntent('check-in')}
                  >
                    我想问一个问题 →
                  </button>
                </div>
              </div>
            </>
          ) : (
            <p className="py-10 text-sm text-muted">章节不存在。</p>
          )}
        </article>

        <aside className="sticky top-[99px] self-start rounded-[14px] border border-border bg-surface p-4 max-lg:hidden">
          <p className="font-mono text-[10px] tracking-wider text-muted">当前学习上下文</p>
          <h3 className="mt-3 font-display text-lg text-fg">{teacherName}知道你正在看什么</h3>
          <div className="mt-4 space-y-3 border-t border-border pt-3">
            <div>
              <span className="text-xs text-muted">书本</span>
              <p className="text-[13px] font-semibold text-fg">{bookTitle}</p>
            </div>
            <div>
              <span className="text-xs text-muted">章节</span>
              <p className="text-[13px] font-semibold text-fg">{detail?.title ?? '…'}</p>
            </div>
            <div>
              <span className="text-xs text-muted">知识点</span>
              <p className="text-[13px] font-semibold text-fg">
                {(detail?.knowledge_points ?? []).map((point) => point.name).join(' · ') || '—'}
              </p>
            </div>
          </div>
          <div className="mt-4 grid gap-2">
            <button
              type="button"
              className="w-full justify-start rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
              onClick={() => void triggerIntent('explain')}
            >
              解释当前内容
            </button>
            <button
              type="button"
              className="w-full justify-start rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
              onClick={() => void triggerIntent('summary')}
            >
              总结本页
            </button>
            <button
              type="button"
              className="w-full justify-start rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
              onClick={() => void triggerIntent('quiz')}
            >
              给我出题
            </button>
          </div>
        </aside>
      </div>

      {popover ? (
        <div
          className="fixed z-34 flex items-center gap-1.5 rounded-[9px] bg-fg p-1.5 text-surface shadow-soft"
          style={{ left: popover.left, top: popover.top }}
        >
          <span className="max-w-[130px] truncate text-[11px]">{popover.text}</span>
          <button
            type="button"
            className="rounded-[6px] bg-surface px-2 py-1 text-[11px] text-fg"
            onClick={() => void askSelected()}
          >
            问{teacherName}
          </button>
        </div>
      ) : null}
    </div>
  )
}
