import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import type { Chapter, ChapterDetail, ContentBlock } from '@/entities/book/types'
import { useCompanionStore } from '@/features/companion'
import type { ConversationIntent } from '@/features/conversation'
import { useConversationStore } from '@/features/conversation'
import { useScreenContext } from '@/features/screen-context'
import { contentService } from '@/mocks/services'

interface PopoverState {
  text: string
  left: number
  top: number
}

function renderMarkedText(text: unknown, mark: unknown) {
  if (typeof text !== 'string') return null
  if (typeof mark !== 'string' || !mark || !text.includes(mark)) return text
  const [before, after] = text.split(mark)
  return (
    <>
      {before}
      <mark className="rounded bg-accent-soft px-1 text-fg">{mark}</mark>
      {after}
    </>
  )
}

function exampleOf(content: Record<string, unknown>): { label: string; text: string } | null {
  const example = content.example
  if (!example || typeof example !== 'object') return null
  const record = example as Record<string, unknown>
  if (typeof record.label !== 'string' || typeof record.text !== 'string') return null
  return { label: record.label, text: record.text }
}

function ContentBlockView({
  block,
  onExplain,
}: {
  block: ContentBlock
  onExplain: () => void
}) {
  const sectionKey = block.section_key ?? undefined

  if (block.block_type === 'TITLE') {
    return (
      <h2 data-read-section={sectionKey} className="font-display text-2xl text-fg">
        {typeof block.content.text === 'string' ? block.content.text : ''}
      </h2>
    )
  }

  if (block.block_type === 'PARAGRAPH' || block.block_type === 'HIGHLIGHT') {
    return (
      <p
        data-read-section={sectionKey}
        className="mb-4 text-base leading-[1.85] text-fg"
      >
        {renderMarkedText(block.content.text, block.content.mark)}
      </p>
    )
  }

  if (block.block_type === 'KNOWLEDGE_CARD') {
    const title = typeof block.content.title === 'string' ? block.content.title : ''
    const text = typeof block.content.text === 'string' ? block.content.text : ''
    const example = exampleOf(block.content)
    return (
      <article
        data-read-section={sectionKey}
        className="my-6 border-y border-border bg-surface px-6 py-5"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="font-mono text-[10px] tracking-wider text-muted">知识卡片</span>
            <h3 className="font-display text-xl text-fg">{title}</h3>
          </div>
          <button
            type="button"
            className="rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
            onClick={onExplain}
          >
            让霜铃讲给我听
          </button>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted">{text}</p>
        {example ? (
          <div className="mt-4 border-l-2 border-fg bg-fg-soft px-4 py-3">
            <strong className="block text-xs text-fg">{example.label}</strong>
            <span className="mt-1 block text-[13px] text-muted">{example.text}</span>
          </div>
        ) : null}
      </article>
    )
  }

  if (block.block_type === 'EXAMPLE') {
    const text = typeof block.content.text === 'string' ? block.content.text : ''
    return (
      <div data-read-section={sectionKey} className="my-5 border-l-2 border-fg bg-fg-soft px-4 py-3">
        <strong className="block text-xs text-fg">生活里的例子</strong>
        <span className="mt-1 block text-[13px] text-muted">{text}</span>
      </div>
    )
  }

  if (block.block_type === 'CALLOUT') {
    const title = typeof block.content.title === 'string' ? block.content.title : ''
    const text = typeof block.content.text === 'string' ? block.content.text : ''
    return (
      <aside data-read-section={sectionKey} className="my-6 border-l-2 border-fg bg-surface px-5 py-4">
        <strong className="font-display text-lg text-fg">{title}</strong>
        <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
      </aside>
    )
  }

  if (block.block_type === 'FIGURE') {
    const caption = typeof block.content.caption === 'string' ? block.content.caption : ''
    const ariaLabel = typeof block.content.aria_label === 'string' ? block.content.aria_label : ''
    return (
      <figure data-read-section={sectionKey} className="my-6">
        <div
          role="img"
          aria-label={ariaLabel}
          className="grid h-36 place-items-center rounded-lg border border-border bg-fg-soft text-sm text-muted"
        >
          图解占位 · {ariaLabel}
        </div>
        {caption ? (
          <figcaption className="mt-2 font-mono text-[10px] tracking-wide text-muted">
            {caption}
          </figcaption>
        ) : null}
      </figure>
    )
  }

  return null
}

export default function ReaderPage() {
  const { bookId = 'b1', chapterId = 'ch3' } = useParams()
  const navigate = useNavigate()
  const { setScreenContext } = useScreenContext()
  const runIntent = useConversationStore((state) => state.runIntent)

  const [bookTitle, setBookTitle] = useState('书本')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [detail, setDetail] = useState<ChapterDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [popover, setPopover] = useState<PopoverState | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setNotice(null)
    setPopover(null)
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
      setNotice(current && current.content_blocks.length === 0 ? '本章暂无内容（原型仅提供第 3 章内容）' : null)
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [bookId, chapterId])

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
          const blockId = element.closest('[data-block-id]')?.getAttribute('data-block-id')
          setScreenContext({
            visibleSection: element.dataset.readSection,
            contentBlockId: blockId ?? undefined,
          })
        }
      },
      { rootMargin: '-18% 0px -55% 0px' },
    )
    container.querySelectorAll('[data-read-section]').forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [detail, setScreenContext])

  // 选中文字 → popover（对齐 0-B §2.3，仅 reader 内容区有效）
  useEffect(() => {
    const onSelectionChange = () => {
      const selection = window.getSelection()
      const text = selection?.toString().trim() ?? ''
      const node = selection?.anchorNode?.parentElement
      if (!text || !node || !node.closest('[data-read-container]')) {
        setPopover(null)
        return
      }
      const selected = text.slice(0, 50)
      setScreenContext({ selectedText: selected })
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
  }, [setScreenContext])

  const triggerIntent = (intent: ConversationIntent) => {
    runIntent(intent)
    useCompanionStore.getState().setOpen(true)
  }

  const askSelected = () => {
    if (!popover) return
    runIntent('selected', popover.text)
    useCompanionStore.getState().setOpen(true)
    window.getSelection()?.removeAllRanges()
    setPopover(null)
  }

  const chapterIndex = chapters.findIndex((chapter) => chapter.chapter_id === chapterId)

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
            onClick={() => triggerIntent('summary')}
          >
            总结本页
          </button>
          <button
            type="button"
            className="rounded-[10px] border border-border bg-surface px-2.5 py-1.5 text-xs text-fg hover:border-fg"
            onClick={() => triggerIntent('quiz')}
          >
            给我出题
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[196px_minmax(0,1fr)_248px] gap-7 pt-8 max-lg:grid-cols-[180px_minmax(0,1fr)] max-md:grid-cols-1">
        <aside className="sticky top-[99px] self-start max-md:static max-md:flex max-md:gap-2 max-md:overflow-x-auto">
          <p className="mb-3 font-mono text-[10px] tracking-wider text-muted max-md:hidden">本章目录</p>
          {chapters.map((chapter) => {
            const active = chapter.chapter_id === chapterId
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
                    <ContentBlockView block={block} onExplain={() => triggerIntent('explain')} />
                  </div>
                ))}
                {notice ? (
                  <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted">
                    {notice}
                  </p>
                ) : null}
                <div className="mt-8 flex items-center justify-between border-t border-fg pt-4">
                  <span className="text-xs text-muted">读到这里了吗？选择一段文字，直接问霜铃。</span>
                  <button
                    type="button"
                    className="rounded-[10px] bg-accent px-3 py-2 text-xs text-surface hover:bg-accent/85"
                    onClick={() => triggerIntent('check-in')}
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
          <h3 className="mt-3 font-display text-lg text-fg">霜铃知道你正在看什么</h3>
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
              onClick={() => triggerIntent('explain')}
            >
              解释当前内容
            </button>
            <button
              type="button"
              className="w-full justify-start rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
              onClick={() => triggerIntent('summary')}
            >
              总结本页
            </button>
            <button
              type="button"
              className="w-full justify-start rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
              onClick={() => triggerIntent('quiz')}
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
            onClick={askSelected}
          >
            问霜铃
          </button>
        </div>
      ) : null}
    </div>
  )
}
