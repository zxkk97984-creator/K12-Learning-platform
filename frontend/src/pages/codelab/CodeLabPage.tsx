import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import type { CodeReview, CodeRun, CodeTask } from '@/shared/api'
import { codeLabService } from '@/shared/services'
import { ResourceState } from '@/shared/ui/ResourceState'
import { useToastStore } from '@/features/feedback'

import { AiReviewPanel } from './components/AiReviewPanel'
import { CodeEditor } from './components/CodeEditor'
import { CodeOutputPanel } from './components/CodeOutputPanel'

/**
 * CodeLab 工作台：写代码 → 运行 → 看输出 → 请 AI 评价。
 *
 * 两个操作都是"就地等待"的同步请求：
 * - 运行：真实 Docker 沙箱执行，通常 1–3 秒。
 * - 请求 AI 评价：后端在同一次请求里跑确定性测试 + 一次 LLM 调用，
 *   可能等待数十秒，所以按钮上必须有明确的进行中文案。
 *
 * 这里刻意没有做自动保存草稿：本轮目标是闭环可用，草稿持久化留待下一阶段。
 */
export default function CodeLabPage() {
  const { taskId = '' } = useParams()
  const showToast = useToastStore((state) => state.showToast)

  const [task, setTask] = useState<CodeTask | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [code, setCode] = useState('')
  const [run, setRun] = useState<CodeRun | null>(null)
  const [review, setReview] = useState<CodeReview | null>(null)

  const [running, setRunning] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoadError(null)
    codeLabService
      .getTask(taskId)
      .then((loaded) => {
        setTask(loaded)
        setCode(loaded.starter_code || '')
        setRun(null)
        setReview(null)
      })
      .catch((err: unknown) => {
        setTask(null)
        setLoadError(err instanceof ApiError ? err.message : '任务加载失败')
      })
  }, [taskId])

  useEffect(load, [load])

  const handleRun = useCallback(async () => {
    if (!task || running) return
    setRunning(true)
    setActionError(null)
    // 代码变了，上一次的评审结论对新代码不再有效
    setReview(null)
    try {
      setRun(await codeLabService.runCode(task.task_id, code))
    } catch (err) {
      setRun(null)
      setActionError(err instanceof ApiError ? err.message : '运行失败，请稍后重试')
    } finally {
      setRunning(false)
    }
  }, [task, code, running])

  const handleReview = useCallback(async () => {
    if (!run || reviewing) return
    setReviewing(true)
    setActionError(null)
    try {
      setReview(await codeLabService.requestReview(run.run_id))
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'AI 评价失败，请稍后重试')
    } finally {
      setReviewing(false)
    }
  }, [run, reviewing])

  const handleReset = useCallback(() => {
    if (!task) return
    setCode(task.starter_code || '')
    setRun(null)
    setReview(null)
    setActionError(null)
    showToast('已还原为初始代码')
  }, [task, showToast])

  if (loadError) {
    return (
      <section className="py-6">
        <ResourceState type="error" description={loadError} onRetry={load} />
      </section>
    )
  }
  if (!task) {
    return (
      <section className="py-6">
        <ResourceState type="loading" />
      </section>
    )
  }

  return (
    <section className="py-6">
      <nav className="mb-4 text-xs text-muted">
        <Link to="/codelab" className="hover:text-fg">
          编程练习
        </Link>
        <span className="px-1.5">/</span>
        <span className="text-fg">{task.title}</span>
      </nav>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        {/* ── 左：题目 ── */}
        <div>
          <h1 className="font-display text-xl text-fg">{task.title}</h1>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted">
            {task.description}
          </p>
          <p className="mt-3 text-xs text-muted">
            {task.has_tests
              ? '本题配置了自动测试：正确性由测试结果决定，AI 负责评价算法与代码质量。'
              : '本题没有自动测试：AI 只评价算法与代码质量，无法判定功能是否正确。'}
          </p>
        </div>

        {/* ── 右：工作台 ── */}
        <div className="space-y-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void handleRun()}
                disabled={running || reviewing}
                className="min-h-[40px] rounded-[10px] bg-accent px-4 text-sm text-surface transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {running ? '运行中…' : '运行'}
              </button>
              <button
                type="button"
                onClick={() => void handleReview()}
                disabled={!run || running || reviewing}
                className="min-h-[40px] rounded-[10px] border border-border bg-surface px-4 text-sm text-fg transition-colors hover:border-fg disabled:opacity-50"
                title={run ? undefined : '请先运行一次代码'}
              >
                {reviewing ? 'AI 评价中…（可能需要几十秒）' : '请 AI 评价'}
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={running || reviewing}
                className="min-h-[40px] rounded-[10px] px-3 text-sm text-muted hover:bg-fg-soft hover:text-fg disabled:opacity-50"
              >
                还原初始代码
              </button>
              <span className="text-xs text-muted">Ctrl / ⌘ + Enter 运行</span>
            </div>

            <CodeEditor
              value={code}
              onChange={setCode}
              onRun={() => void handleRun()}
              readOnly={running || reviewing}
            />
          </div>

          {actionError ? (
            <p role="alert" className="rounded-[10px] border border-danger/40 bg-danger/5 p-2.5 text-xs text-danger">
              {actionError}
            </p>
          ) : null}

          <section className="rounded-[10px] border border-border bg-surface p-3">
            <h2 className="mb-2 text-xs font-semibold text-fg">运行结果</h2>
            <CodeOutputPanel run={run} />
          </section>

          <section className="rounded-[10px] border border-border bg-surface p-3">
            <h2 className="mb-2 text-xs font-semibold text-fg">AI 编程评价</h2>
            <AiReviewPanel review={review} />
          </section>
        </div>
      </div>
    </section>
  )
}
