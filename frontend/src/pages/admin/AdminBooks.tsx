import { useEffect, useState } from 'react'

import type { AdminBook } from '@/entities/admin/types'
import { useToastStore } from '@/features/feedback'
import { adminService } from '@/shared/api/admin-service'

export function AdminBooks() {
  const [books, setBooks] = useState<AdminBook[]>([])
  const [title, setTitle] = useState('')
  const [gradeMin, setGradeMin] = useState(7)
  const [gradeMax, setGradeMax] = useState(9)
  const [tags, setTags] = useState('')
  const showToast = useToastStore((state) => state.showToast)

  const load = () => {
    void adminService.getBooks().then(setBooks).catch(() => setBooks([]))
  }

  useEffect(load, [])

  const create = async () => {
    try {
      await adminService.createBook({
        title,
        grade_min: gradeMin,
        grade_max: gradeMax,
        tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean),
      })
      showToast('书籍已创建')
      setTitle('')
      load()
    } catch {
      showToast('创建失败，请重试')
    }
  }

  const setStatus = async (book: AdminBook, status: AdminBook['status']) => {
    try {
      await adminService.patchBook(book.book_id, { status })
      showToast('状态已更新')
      load()
    } catch {
      showToast('状态更新失败')
    }
  }

  return (
    <div className="grid max-w-3xl gap-4">
      <section className="rounded-[14px] border border-border bg-surface p-4">
        <h2 className="font-display text-lg text-fg">新建书籍</h2>
        <div className="mt-3 grid gap-2">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="书名"
            aria-label="书名"
            className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
          <div className="flex gap-2">
            <input
              type="number"
              value={gradeMin}
              onChange={(event) => setGradeMin(Number(event.target.value))}
              aria-label="起始年级"
              className="h-10 w-24 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
            />
            <input
              type="number"
              value={gradeMax}
              onChange={(event) => setGradeMax(Number(event.target.value))}
              aria-label="结束年级"
              className="h-10 w-24 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
            />
          </div>
          <input
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="标签，逗号分隔"
            aria-label="标签"
            className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
          <button
            type="button"
            className="rounded-[10px] bg-accent px-4 py-2 text-sm text-surface"
            onClick={() => void create()}
          >
            创建书籍
          </button>
        </div>
      </section>

      <ul className="grid gap-2">
        {books.map((book) => (
          <li key={book.book_id} className="flex items-center gap-3 rounded-[12px] border border-border bg-surface p-3">
            <div className="min-w-0 flex-1">
              <strong className="text-sm text-fg">{book.title}</strong>
              <p className="text-[11px] text-muted">
                {book.grade_min}~{book.grade_max} · {book.status} · {book.tags.join('、')}
              </p>
            </div>
            {book.status !== 'PUBLISHED' ? (
              <button
                type="button"
                className="rounded-md border border-border px-2.5 py-1 text-[11px] text-fg"
                onClick={() => void setStatus(book, 'PUBLISHED')}
              >
                发布
              </button>
            ) : (
              <button
                type="button"
                className="rounded-md border border-border px-2.5 py-1 text-[11px] text-muted"
                onClick={() => void setStatus(book, 'ARCHIVED')}
              >
                下架
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
