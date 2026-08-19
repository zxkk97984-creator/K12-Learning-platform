import { useEffect, useState } from 'react'

import type { AdminStats } from '@/entities/admin/types'
import { adminService } from '@/shared/api/admin-service'

export function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null)

  useEffect(() => {
    void adminService.getStats().then(setStats).catch(() => setStats(null))
  }, [])

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
