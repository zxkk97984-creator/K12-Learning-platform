import { useState } from 'react'

import type { MemoryAction } from '@/shared/api/memory-service'
import type { StudentMemory } from '@/entities/memory/types'
import { useToastStore } from '@/features/feedback'
import { useTeacherName } from '@/features/companion'
import { memoryService } from '@/shared/services'

interface MemoryListProps {
  memories: StudentMemory[]
  onChanged: () => void
}

function actionToast(teacherName: string): Record<MemoryAction, string> {
  return {
    CONFIRM: `已确认，${teacherName}会继续使用这条记忆`,
    DISPUTE: `已标记为「不完全正确」，${teacherName}会重新验证`,
    EDIT: '已保存修改',
    FORGET: `已忘记这条记忆，${teacherName}不会再使用`,
  }
}

export function MemoryList({ memories, onChanged }: MemoryListProps) {
  const showToast = useToastStore((state) => state.showToast)
  const teacherName = useTeacherName()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  const runAction = async (memory: StudentMemory, action: MemoryAction, content?: string) => {
    try {
      await memoryService.updateMemory(memory.memory_id, action, content)
      showToast(actionToast(teacherName)[action])
      setEditingId(null)
      onChanged()
    } catch {
      showToast('操作失败，请重试')
    }
  }

  return (
    <ul className="grid gap-3">
      {memories.map((memory) => {
        const editing = editingId === memory.memory_id
        return (
          <li key={memory.memory_id} className="min-w-0 rounded-[10px] border border-border bg-surface p-3">
            {editing ? (
              <div>
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={2}
                  className="w-full resize-none rounded-lg border border-border bg-bg px-2.5 py-2 text-xs text-fg outline-none focus:border-fg"
                />
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="rounded-md bg-accent px-2.5 py-1 text-[11px] text-surface"
                    onClick={() => void runAction(memory, 'EDIT', draft)}
                  >
                    保存
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
                <p className="text-xs leading-relaxed text-fg wrap-anywhere">{memory.content}</p>
                {memory.tags.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {memory.tags.map((tag) => (
                      <span key={tag} className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted">
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-1">
                  <button
                    type="button"
                    className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                    onClick={() => void runAction(memory, 'CONFIRM')}
                  >
                    正确
                  </button>
                  <button
                    type="button"
                    className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                    onClick={() => void runAction(memory, 'DISPUTE')}
                  >
                    不完全正确
                  </button>
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
                  <button
                    type="button"
                    className="rounded-md px-2 py-1 text-[10px] text-muted hover:bg-fg-soft hover:text-fg"
                    onClick={() => void runAction(memory, 'FORGET')}
                  >
                    忘记这条
                  </button>
                </div>
              </>
            )}
          </li>
        )
      })}
    </ul>
  )
}
