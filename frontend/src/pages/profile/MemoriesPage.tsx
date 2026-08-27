import { useCallback, useEffect, useState } from 'react'

import type { MemoryEvidence, MemoryStatus, StudentMemory } from '@/entities/memory/types'
import type { MemoryAction, MemoryListParams } from '@/shared/api/memory-service'
import { useToastStore } from '@/features/feedback'
import { useTeacherName } from '@/features/companion'
import { memoryService } from '@/shared/services'

type MemoryFilter = Extract<MemoryStatus, 'ACTIVE' | 'DISPUTED' | 'REMOVED'>

const FILTERS: Array<[MemoryFilter, string]> = [
  ['ACTIVE', '当前记忆'],
  ['DISPUTED', '待重新确认'],
  ['REMOVED', '已忘记'],
]

const STATUS_LABEL: Record<MemoryStatus, string> = {
  ACTIVE: '当前使用中',
  DISPUTED: '待重新确认',
  SUPERSEDED: '已被新版本替代',
  REMOVED: '已忘记',
}

const SOURCE_LABEL: Record<MemoryEvidence['source_type'], string> = {
  QUIZ: '测验记录',
  LEARNING_SESSION: '学习时段',
  CONVERSATION: '课程对话',
  BOOK_PROGRESS: '阅读进度',
}

function actionToast(teacherName: string): Record<MemoryAction, string> {
  return {
    CONFIRM: `已确认，${teacherName}会继续使用这条记忆`,
    DISPUTE: `已标记为「不完全正确」，${teacherName}会重新验证`,
    EDIT: '已保存修改',
    FORGET: `已忘记这条记忆，${teacherName}不会再使用`,
  }
}

function payloadText(payload: Record<string, unknown>): string {
  return Object.entries(payload)
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(' · ')
}

export default function MemoriesPage() {
  const showToast = useToastStore((state) => state.showToast)
  const teacherName = useTeacherName()
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [statusFilter, setStatusFilter] = useState<MemoryFilter>('ACTIVE')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [evidenceById, setEvidenceById] = useState<Record<string, MemoryEvidence>>({})
  const [evidenceLoadingId, setEvidenceLoadingId] = useState<string | null>(null)

  const load = useCallback(async (filter: MemoryFilter) => {
    setLoading(true)
    setError(null)
    const params: MemoryListParams = { status: filter }
    try {
      setMemories(await memoryService.getMemories(params))
    } catch {
      setMemories([])
      setError('记忆暂时加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(statusFilter)
  }, [load, statusFilter])

  const runAction = async (memory: StudentMemory, action: MemoryAction, content?: string) => {
    if (action === 'EDIT' && !content?.trim()) {
      showToast('记忆内容不能为空')
      return
    }
    try {
      await memoryService.updateMemory(memory.memory_id, action, content)
      showToast(actionToast(teacherName)[action])
      setEditingId(null)

      // DISPUTED/REMOVED 有独立筛选页，操作后切到结果所在的列表，便于继续确认或复核。
      const nextFilter: MemoryFilter =
        action === 'DISPUTE' ? 'DISPUTED' : action === 'FORGET' ? 'REMOVED' : 'ACTIVE'
      setStatusFilter(nextFilter)
      await load(nextFilter)
    } catch {
      showToast('操作失败，请重试')
    }
  }

  const toggleEvidence = async (memory: StudentMemory) => {
    if (expandedId === memory.memory_id) {
      setExpandedId(null)
      return
    }
    setExpandedId(memory.memory_id)
    const missingIds = memory.evidence_ids.filter((evidenceId) => !evidenceById[evidenceId])
    if (missingIds.length === 0) return

    setEvidenceLoadingId(memory.memory_id)
    try {
      const entries = await Promise.all(
        missingIds.map(async (evidenceId) => [evidenceId, await memoryService.getEvidence(evidenceId)] as const),
      )
      setEvidenceById((current) => Object.fromEntries([...Object.entries(current), ...entries]))
    } catch {
      showToast('证据详情暂时不可用')
    } finally {
      setEvidenceLoadingId(null)
    }
  }

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">成长 · 记忆管理</p>
      <h1 className="mt-3 font-display text-4xl text-fg">AI 记得什么</h1>
      <p className="mt-2 max-w-[52ch] text-sm text-muted">
        {teacherName}对你的每条理解都来自真实学习记录。你可以确认、质疑、修改或忘记。
      </p>
      <p className="mt-2 text-xs text-muted">记忆由学习记录与 Memory Skill 生成，当前不支持手动添加。</p>

      <div className="mt-6 flex max-w-2xl flex-wrap gap-1 rounded-[10px] bg-fg-soft p-1">
        {FILTERS.map(([filter, label]) => (
          <button
            key={filter}
            type="button"
            aria-pressed={statusFilter === filter}
            className={`rounded-lg px-3 py-1.5 text-xs ${
              statusFilter === filter ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
            }`}
            onClick={() => setStatusFilter(filter)}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="max-w-2xl py-8 text-center text-sm text-muted">正在加载记忆…</p>
      ) : error ? (
        <div className="mt-6 max-w-2xl rounded-[10px] border border-border bg-surface p-4 text-sm text-muted">
          <p>{error}</p>
          <button
            type="button"
            className="mt-3 rounded-md border border-border px-2.5 py-1 text-xs text-fg hover:border-fg"
            onClick={() => void load(statusFilter)}
          >
            重试
          </button>
        </div>
      ) : memories.length === 0 ? (
        <div className="mt-6 max-w-2xl rounded-[10px] border border-border bg-surface p-6 text-sm text-muted">
          {statusFilter === 'REMOVED' ? '还没有已忘记的记忆。' : '暂时没有符合条件的记忆。'}
        </div>
      ) : (
        <ul className="mt-6 grid max-w-2xl gap-3">
          {memories.map((memory) => {
            const editing = editingId === memory.memory_id
            const removed = memory.status === 'REMOVED'
            return (
              <li
                key={memory.memory_id}
                className={`rounded-[10px] border border-border bg-surface p-3 ${removed ? 'opacity-65' : ''}`}
              >
                {editing ? (
                  <div>
                    <textarea
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      rows={3}
                      aria-label="修改记忆内容"
                      className="w-full resize-none rounded-lg border border-border bg-bg px-2.5 py-2 text-xs text-fg outline-none focus:border-fg"
                    />
                    <div className="mt-2 flex gap-2">
                      <button
                        type="button"
                        className="rounded-md bg-accent px-2.5 py-1 text-[11px] text-surface"
                        onClick={() => void runAction(memory, 'EDIT', draft)}
                      >
                        保存修改
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-border px-2.5 py-1 text-[11px] text-muted"
                        onClick={() => setEditingId(null)}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start gap-3">
                      <p className="flex-1 text-xs leading-relaxed text-fg">{memory.content}</p>
                      <span className="shrink-0 rounded-full border border-border px-2 py-0.5 font-mono text-[9px] text-muted">
                        {STATUS_LABEL[memory.status]}
                      </span>
                    </div>
                    {memory.tags.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {memory.tags.map((tag) => (
                          <span key={tag} className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted">
                            {tag}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      {memory.user_confirmed ? (
                        <span className="mr-1 text-[10px] text-accent">✓ 已确认</span>
                      ) : null}
                      {!removed && memory.status !== 'DISPUTED' ? (
                        <button
                          type="button"
                          className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                          onClick={() => void runAction(memory, 'CONFIRM')}
                        >
                          确认正确
                        </button>
                      ) : null}
                      {!removed && memory.status === 'DISPUTED' ? (
                        <button
                          type="button"
                          className="rounded-md px-2 py-1 text-[10px] text-accent hover:bg-fg-soft"
                          onClick={() => void runAction(memory, 'CONFIRM')}
                        >
                          再次确认
                        </button>
                      ) : null}
                      {!removed && memory.status === 'ACTIVE' ? (
                        <button
                          type="button"
                          className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                          onClick={() => void runAction(memory, 'DISPUTE')}
                        >
                          质疑
                        </button>
                      ) : null}
                      {!removed ? (
                        <button
                          type="button"
                          className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                          onClick={() => {
                            setDraft(memory.content)
                            setEditingId(memory.memory_id)
                          }}
                        >
                          修改
                        </button>
                      ) : null}
                      {!removed ? (
                        <button
                          type="button"
                          className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                          onClick={() => void runAction(memory, 'FORGET')}
                        >
                          忘记这条
                        </button>
                      ) : null}
                      {memory.evidence_ids.length > 0 ? (
                        <button
                          type="button"
                          aria-expanded={expandedId === memory.memory_id}
                          className="ml-auto rounded-md px-2 py-1 text-[10px] text-fg hover:bg-fg-soft"
                          onClick={() => void toggleEvidence(memory)}
                        >
                          {expandedId === memory.memory_id ? '收起依据' : '为什么？'}
                        </button>
                      ) : null}
                    </div>
                    {expandedId === memory.memory_id ? (
                      <div className="mt-3 border-t border-border pt-3">
                        <p className="font-mono text-[10px] text-muted">这条记忆来自：</p>
                        {evidenceLoadingId === memory.memory_id ? (
                          <p className="mt-2 text-[11px] text-muted">正在读取依据…</p>
                        ) : (
                          <div className="mt-2 grid gap-2">
                            {memory.evidence_ids.map((evidenceId) => {
                              const evidence = evidenceById[evidenceId]
                              return evidence ? (
                                <div key={evidenceId} className="rounded-lg bg-fg-soft p-2 text-[11px] text-muted">
                                  <strong className="text-fg">{SOURCE_LABEL[evidence.source_type]}</strong>
                                  <p className="mt-1">{payloadText(evidence.payload)}</p>
                                  <p className="mt-1 font-mono text-[9px]">
                                    {evidence.count} 条记录 · {evidence.last_occurred_at?.slice(0, 10) ?? '时间未知'}
                                  </p>
                                </div>
                              ) : null
                            })}
                          </div>
                        )}
                      </div>
                    ) : null}
                  </>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
