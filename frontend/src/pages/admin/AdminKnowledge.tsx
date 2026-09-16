import { useCallback, useEffect, useRef, useState } from 'react'

import type { AdminKnowledgeResource } from '@/entities/admin/types'
import { useToastStore } from '@/features/feedback'
import { adminService } from '@/shared/api/admin-service'
import { ApiError } from '@/shared/api/http'

const STATUS_LABEL: Record<string, string> = {
  READY: '已就绪',
  FAILED: '处理失败',
  UPLOADED: '已上传，正在处理',
  PARSING: '解析中',
  CHUNKING: '切块中',
  INDEXING: '索引中',
}

const NON_TERMINAL = new Set(['UPLOADED', 'PARSING', 'CHUNKING', 'INDEXING'])
const POLL_INTERVAL_MS = 3000
const STALE_MS = 120_000

/** T21：状态非终态每 3s 轮询；页面隐藏暂停；卸载取消；READY/FAILED 停止；超 2 分钟提示仍在处理。 */
export function AdminKnowledge() {
  const [resources, setResources] = useState<AdminKnowledgeResource[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [sourceName, setSourceName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [author, setAuthor] = useState('')
  const [license, setLicense] = useState('CC-BY-4.0')
  const [copyrightStatus, setCopyrightStatus] = useState('示例资源')
  const [uploading, setUploading] = useState(false)
  const [reprocessing, setReprocessing] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const showToast = useToastStore((state) => state.showToast)
  const pollingRef = useRef<number | null>(null)

  const load = useCallback(async () => {
    try {
      const list = await adminService.getKnowledgeResources()
      setResources(list)
      setLoadError(null)
      return list
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : '加载资源失败')
      return []
    }
  }, [])

  // 轮询：仅当存在非终态资源时每 3s 刷新；页面隐藏暂停；卸载取消。
  useEffect(() => {
    let cancelled = false
    const start = () => {
      if (pollingRef.current !== null) return
      const run = async () => {
        if (document.hidden) return
        const list = await load()
        if (cancelled) return
        setResources(list)
      }
      pollingRef.current = window.setInterval(run, POLL_INTERVAL_MS)
    }
    const stop = () => {
      if (pollingRef.current !== null) {
        window.clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
    const onVisibility = () => {
      if (document.hidden) stop()
      else start()
    }
    // 启动条件：任一资源非终态。
    start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [load])

  // 初次加载。
  useEffect(() => {
    void load()
  }, [load])

  // 资源完成态变化时清空"重新处理中"标记。
  useEffect(() => {
    if (reprocessing && !resources.some((r) => r.resource_id === reprocessing && NON_TERMINAL.has(r.status))) {
      setReprocessing(null)
    }
  }, [resources, reprocessing])

  const hasNonTerminal = resources.some((r) => NON_TERMINAL.has(r.status))

  const upload = async () => {
    if (!file) {
      showToast('请选择文件')
      return
    }
    setUploading(true)
    try {
      await adminService.uploadKnowledgeResource({
        file,
        source_name: sourceName,
        source_url: sourceUrl,
        author: author || undefined,
        license,
        copyright_status: copyrightStatus,
      })
      // 上传成功进入处理 → 轮询会自动跟到 READY/FAILED，无需手刷。
      showToast('已上传，正在处理')
      if (!hasNonTerminal) void load()
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '上传失败，请重试')
    } finally {
      setUploading(false)
    }
  }

  const reprocess = async (resource: AdminKnowledgeResource) => {
    setReprocessing(resource.resource_id)
    try {
      await adminService.reprocessResource(resource.resource_id)
      showToast('已加入处理队列')
      void load()
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : '重新处理失败')
      setReprocessing(null)
    }
  }

  const isStale = (resource: AdminKnowledgeResource) =>
    !!resource.created_at && Date.now() - new Date(resource.created_at).getTime() > STALE_MS

  return (
    <div className="grid max-w-3xl gap-4">
      {loadError ? (
        <div className="rounded-[12px] border border-muted bg-surface p-4 text-sm text-muted" role="alert">
          <strong className="text-fg">暂无法加载资源</strong> · {loadError}
          <button
            type="button"
            className="ml-3 rounded-md border border-border px-2 py-1 text-[11px] text-fg hover:border-fg"
            onClick={() => void load()}
          >
            重试
          </button>
        </div>
      ) : null}

      <section className="rounded-[14px] border border-border bg-surface p-4">
        <h2 className="font-display text-lg text-fg">上传知识资源</h2>
        <div className="mt-3 grid gap-2">
          <input
            type="file"
            accept=".md,.markdown,.txt,.html,.pdf"
            aria-label="选择文件"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="text-xs text-muted"
          />
          <input
            value={sourceName}
            onChange={(event) => setSourceName(event.target.value)}
            placeholder="来源名称"
            aria-label="来源名称"
            className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
          <input
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="来源 URL"
            aria-label="来源 URL"
            className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
          <input
            value={author}
            onChange={(event) => setAuthor(event.target.value)}
            placeholder="作者（可选）"
            aria-label="作者"
            className="h-10 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
          <div className="flex gap-2">
            <input
              value={license}
              onChange={(event) => setLicense(event.target.value)}
              placeholder="License"
              aria-label="License"
              className="h-10 flex-1 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
            />
            <input
              value={copyrightStatus}
              onChange={(event) => setCopyrightStatus(event.target.value)}
              placeholder="版权状态"
              aria-label="版权状态"
              className="h-10 flex-1 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
            />
          </div>
          <button
            type="button"
            disabled={uploading}
            className="rounded-[10px] bg-accent px-4 py-2 text-sm text-surface disabled:opacity-50"
            onClick={() => void upload()}
          >
            {uploading ? '上传中…' : '上传'}
          </button>
        </div>
      </section>

      {hasNonTerminal ? (
        <p className="font-mono text-[10px] text-muted">
          正在自动刷新处理状态（每 3 秒）；有资源超过 2 分钟仍在处理时可手动刷新。
        </p>
      ) : null}

      <ul className="grid gap-2">
        {resources.map((resource) => {
          const busy = reprocessing === resource.resource_id
          return (
            <li key={resource.resource_id} className="rounded-[12px] border border-border bg-surface p-3">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <strong className="text-sm text-fg">{resource.source_name}</strong>
                  <p className="text-[11px] text-muted">{resource.source_url}</p>
                </div>
                <span
                  className={`rounded-full border px-2 py-0.5 font-mono text-[10px] ${
                    resource.status === 'READY'
                      ? 'border-fg text-fg'
                      : resource.status === 'FAILED'
                        ? 'border-muted text-muted'
                        : 'border-accent text-accent'
                  }`}
                >
                  {STATUS_LABEL[resource.status] ?? resource.status}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-md border border-border px-2 py-1 text-[11px] text-muted disabled:opacity-50"
                  onClick={() => void reprocess(resource)}
                >
                  {busy ? '已加入队列…' : '重新处理'}
                </button>
              </div>
              {resource.status === 'FAILED' && resource.error ? (
                <p className="mt-2 text-[11px] text-muted" role="alert">
                  失败原因：{resource.error}
                  {resource.storage_key ? `（资源 ID：${resource.resource_id.slice(0, 8)}）` : ''}
                </p>
              ) : null}
              {NON_TERMINAL.has(resource.status) && isStale(resource) ? (
                <p className="mt-2 text-[11px] text-accent">
                  仍在处理中，可稍后手动刷新，或点击"重新处理"再次尝试。
                </p>
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
