import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import type { CodeTaskListItem } from '@/shared/api'
import { codeLabService } from '@/shared/services'
import { ResourceState } from '@/shared/ui/ResourceState'

/** CodeLab 任务列表。 */
export default function CodeLabListPage() {
  const [tasks, setTasks] = useState<CodeTaskListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    codeLabService
      .listTasks()
      .then(setTasks)
      .catch((err: unknown) => {
        setTasks(null)
        setError(err instanceof ApiError ? err.message : '编程任务加载失败')
      })
  }

  useEffect(load, [])

  return (
    <section className="py-6">
      <header className="mb-5">
        <h1 className="font-display text-2xl text-fg">编程练习</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          在浏览器里编写并运行 Python 代码，运行结果由真实的隔离沙箱给出，完成后可以请 AI 评价你的算法思路与代码质量。
        </p>
      </header>

      {error ? (
        <ResourceState type="error" description={error} onRetry={load} />
      ) : tasks === null ? (
        <ResourceState type="loading" />
      ) : tasks.length === 0 ? (
        <ResourceState type="empty" description="暂时还没有可用的编程任务。" />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2" data-testid="codelab-task-list">
          {tasks.map((task) => (
            <li key={task.task_id}>
              <Link
                to={`/codelab/${task.task_id}`}
                className="block h-full rounded-[10px] border border-border bg-surface p-4 transition-colors hover:border-fg"
              >
                <h2 className="font-display text-base text-fg">{task.title}</h2>
                <p className="mt-1.5 line-clamp-3 text-sm leading-relaxed text-muted">
                  {task.description}
                </p>
                <p className="mt-3 text-xs text-muted">
                  {task.has_tests ? '含自动测试' : '不含自动测试（只评代码质量）'}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
