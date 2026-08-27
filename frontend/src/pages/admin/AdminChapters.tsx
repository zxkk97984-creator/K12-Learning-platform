import { useEffect, useState } from 'react'

import type { Book } from '@/entities/book/types'
import type { Chapter, ChapterDetail } from '@/entities/book/types'
import { contentService } from '@/shared/services'
import { adminService } from '@/shared/api/admin-service'

/** 章节 / 内容块 / 知识点管理（Phase 4）：读写均走真实 API。 */
export function AdminChapters() {
  const [books, setBooks] = useState<Book[]>([])
  const [bookId, setBookId] = useState<string>('')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [chapterId, setChapterId] = useState<string>('')
  const [detail, setDetail] = useState<ChapterDetail | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [blockText, setBlockText] = useState('')
  const [kpName, setKpName] = useState('')
  const [kpSlug, setKpSlug] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const list = await contentService.getBooks()
        setBooks(list)
        if (list[0]) setBookId(list[0].book_id)
      } catch {
        setBooks([])
      }
    })()
  }, [])

  useEffect(() => {
    if (!bookId) return
    void (async () => {
      try {
        setChapters(await contentService.getChapters(bookId))
        setChapterId('')
        setDetail(null)
      } catch {
        setChapters([])
      }
    })()
  }, [bookId])

  useEffect(() => {
    if (!chapterId) return
    void (async () => {
      try {
        setDetail(await contentService.getChapter(chapterId))
      } catch {
        setDetail(null)
      }
    })()
  }, [chapterId])

  const addChapter = async () => {
    if (!bookId || !newTitle.trim()) return
    try {
      // Phase 4 验收：chapter_order 由后端独占生成（max+1），前端不传
      await adminService.createChapter(bookId, {
        title: newTitle.trim(),
        estimated_minutes: 10,
      })
      setNewTitle('')
      setChapters(await contentService.getChapters(bookId))
      setMessage('章节已创建')
    } catch {
      setMessage('章节创建失败')
    }
  }

  const publishChapter = async () => {
    if (!chapterId) return
    try {
      await adminService.patchChapter(chapterId, { status: 'PUBLISHED' })
      setChapters(await contentService.getChapters(bookId))
      setMessage('章节已发布')
    } catch {
      setMessage('发布失败')
    }
  }

  const addBlock = async () => {
    if (!chapterId || !blockText.trim()) return
    try {
      await adminService.createContentBlock(chapterId, {
        block_type: 'PARAGRAPH',
        content: { text: blockText.trim() },
        block_order: (detail?.content_blocks.length ?? 0) + 1,
        section_key: '新段落',
      })
      setBlockText('')
      setDetail(await contentService.getChapter(chapterId))
      setMessage('内容块已添加')
    } catch {
      setMessage('内容块添加失败')
    }
  }

  const addKp = async () => {
    if (!kpName.trim() || !kpSlug.trim()) return
    try {
      await adminService.createKnowledgePoint({
        name: kpName.trim(),
        slug: kpSlug.trim(),
      })
      setKpName('')
      setKpSlug('')
      setMessage('知识点已创建')
    } catch {
      setMessage('知识点创建失败（slug 可能重复）')
    }
  }

  return (
    <section className="space-y-4">
      <h1 className="font-display text-2xl text-fg">章节 / 内容块 / 知识点</h1>
      {message ? (
        <p role="status" className="text-xs text-accent">
          {message}
        </p>
      ) : null}

      <label className="block text-sm text-muted">
        选择书籍
        <select
          data-testid="admin-book-select"
          value={bookId}
          onChange={(event) => setBookId(event.target.value)}
          className="ml-2 rounded-lg border border-border bg-surface px-2 py-1.5 text-fg"
        >
          {books.map((book) => (
            <option key={book.book_id} value={book.book_id}>
              {book.title}
            </option>
          ))}
        </select>
      </label>

      <div className="rounded-[12px] border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-fg">章节列表</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {chapters.map((chapter) => (
            <li key={chapter.chapter_id}>
              <button
                type="button"
                onClick={() => setChapterId(chapter.chapter_id)}
                className={`rounded px-1.5 py-0.5 ${
                  chapterId === chapter.chapter_id ? 'bg-fg-soft text-fg' : 'text-muted hover:text-fg'
                }`}
              >
                {chapter.chapter_order}. {chapter.title}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex gap-2">
          <input
            aria-label="新章节标题"
            placeholder="新章节标题"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            className="flex-1 rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
          />
          <button
            type="button"
            onClick={() => void addChapter()}
            className="rounded-lg border border-border px-3 text-sm text-fg hover:border-fg"
          >
            创建章节
          </button>
          {chapterId ? (
            <button
              type="button"
              onClick={() => void publishChapter()}
              className="rounded-lg border border-fg bg-fg px-3 text-sm text-surface"
            >
              发布本章
            </button>
          ) : null}
        </div>
      </div>

      {detail ? (
        <div className="rounded-[12px] border border-border bg-surface p-4">
          <h2 className="text-sm font-semibold text-fg">
            内容块 · {detail.title}（{detail.content_blocks.length}）
          </h2>
          <ol className="mt-2 list-inside list-decimal space-y-1 text-xs text-muted">
            {detail.content_blocks.map((block) => (
              <li key={block.block_id}>
                [{block.block_type}] {String(block.content.text ?? block.content.caption ?? '').slice(0, 40)}
              </li>
            ))}
          </ol>
          <div className="mt-3 flex gap-2">
            <input
              aria-label="新段落文本"
              placeholder="新段落文本"
              value={blockText}
              onChange={(event) => setBlockText(event.target.value)}
              className="flex-1 rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
            />
            <button
              type="button"
              onClick={() => void addBlock()}
              className="rounded-lg border border-border px-3 text-sm text-fg hover:border-fg"
            >
              追加段落块
            </button>
          </div>

          <h2 className="mt-4 text-sm font-semibold text-fg">知识点</h2>
          <p className="mt-1 text-xs text-muted">
            {detail.knowledge_points.length > 0
              ? detail.knowledge_points.map((point) => point.name).join('、')
              : '暂无知识点'}
          </p>
          <div className="mt-2 flex gap-2">
            <input
              aria-label="知识点名称"
              placeholder="名称"
              value={kpName}
              onChange={(event) => setKpName(event.target.value)}
              className="rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
            />
            <input
              aria-label="知识点 slug"
              placeholder="slug"
              value={kpSlug}
              onChange={(event) => setKpSlug(event.target.value)}
              className="rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
            />
            <button
              type="button"
              onClick={() => void addKp()}
              className="rounded-lg border border-border px-3 text-sm text-fg hover:border-fg"
            >
              创建知识点
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
