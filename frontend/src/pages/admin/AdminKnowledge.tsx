import { useEffect, useState } from 'react'

import type { AdminKnowledgeResource } from '@/entities/admin/types'
import { useToastStore } from '@/features/feedback'
import { adminService } from '@/shared/api/admin-service'

const STATUS_LABEL: Record<string, string> = {
  READY: '已就绪',
  FAILED: '处理失败',
  UPLOADED: '已上传',
  PARSING: '解析中',
  CHUNKING: '切块中',
  INDEXING: '索引中',
}

export function AdminKnowledge() {
  const [resources, setResources] = useState<AdminKnowledgeResource[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [sourceName, setSourceName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [author, setAuthor] = useState('')
  const [license, setLicense] = useState('CC-BY-4.0')
  const [copyrightStatus, setCopyrightStatus] = useState('示例资源')
  const showToast = useToastStore((state) => state.showToast)

  const load = () => {
    void adminService.getKnowledgeResources().then(setResources).catch(() => setResources([]))
  }

  useEffect(load, [])

  const upload = async () => {
    if (!file) {
      showToast('请选择文件')
      return
    }
    try {
      await adminService.uploadKnowledgeResource({
        file,
        source_name: sourceName,
        source_url: sourceUrl,
        author: author || undefined,
        license,
        copyright_status: copyrightStatus,
      })
      showToast('上传完成')
      setFile(null)
      load()
    } catch {
      showToast('上传失败，请重试')
    }
  }

  const reprocess = async (resource: AdminKnowledgeResource) => {
    try {
      await adminService.reprocessResource(resource.resource_id)
      showToast('已重新处理')
      load()
    } catch {
      showToast('重新处理失败')
    }
  }

  return (
    <div className="grid max-w-3xl gap-4">
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
            className="rounded-[10px] bg-accent px-4 py-2 text-sm text-surface"
            onClick={() => void upload()}
          >
            上传
          </button>
        </div>
      </section>

      <ul className="grid gap-2">
        {resources.map((resource) => (
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
                className="rounded-md border border-border px-2 py-1 text-[11px] text-muted"
                onClick={() => void reprocess(resource)}
              >
                重新处理
              </button>
            </div>
            {resource.error ? (
              <p className="mt-2 text-[11px] text-muted">失败原因：{resource.error}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
