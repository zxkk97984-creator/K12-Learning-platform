import { useEffect, useState } from 'react'

import type { AdminStats } from '@/entities/admin/types'
import { adminService } from '@/shared/api/admin-service'
import { ApiError } from '@/shared/api/http'

export function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setError(null)
    void adminService
      .getStats()
      .then((value) => {
        if (active) setStats(value)
      })
      .catch((err: unknown) => {
        if (active) {
          setStats(null)
          setError(err instanceof ApiError ? err.message : '统计加载失败')
        }
      })
    return () => {
      active = false
    }
  }, [attempt])

  const cards = stats
    ? [
        ['书籍总数', stats.books_total],
        ['已发布', stats.books_published],
        ['章节', stats.chapters_total],
        ['知识点', stats.knowledge_points_total],
        ['资源总数', stats.resources_total],
        ['资源就绪', stats.resources_ready],
        ['资源失败', stats.resources_failed],
        ['学生数', stats.students_total],
      ]
    : []

  if (error) {
    return (
      <div className="max-w-3xl rounded-[14px] border border-border bg-surface p-5" role="alert">
        <strong className="text-fg">统计加载失败</strong>
        <p className="mt-1 text-sm text-muted">{error}</p>
        <button
          type="button"
          className="mt-3 rounded-[10px] bg-accent px-4 py-2 text-sm text-surface hover:bg-accent/85"
          onClick={() => setAttempt((value) => value + 1)}
        >
          重新加载
        </button>
      </div>
    )
  }

  return (
    <div className="grid max-w-3xl gap-3 sm:grid-cols-2">
      {cards.length === 0 ? (
        <p className="text-sm text-muted">正在加载统计…</p>
      ) : (
        cards.map(([label, value]) => (
          <div key={label} className="rounded-[14px] border border-border bg-surface p-4">
            <p className="font-mono text-[10px] text-muted">{label}</p>
            <p className="mt-1.5 font-display text-2xl text-fg">{value}</p>
          </div>
        ))
      )}
    </div>
  )
}
