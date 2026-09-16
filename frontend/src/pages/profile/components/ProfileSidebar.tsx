import type { StudentMemory } from '@/entities/memory/types'
import { MemoryList } from '@/features/memory'

interface ProfileSidebarProps {
  teacherName: string
  memories: StudentMemory[]
  onChanged: () => void
  onAskWhy: () => void
  onOpenArchive: () => void
  /** 进入记忆管理页（T09 布局修正：并入右栏，不再作为第三个网格子元素） */
  onManageMemories: () => void
}

/** 右栏：证据说明 + AI 记忆列表 + 对话入口 + 管理记忆 */
export function ProfileSidebar({
  teacherName,
  memories,
  onChanged,
  onAskWhy,
  onOpenArchive,
  onManageMemories,
}: ProfileSidebarProps) {
  return (
    <aside className="grid content-start gap-6 rounded-[14px] border border-border bg-surface p-5 min-w-0">
      <section>
        <p className="font-mono text-xs text-muted">证据覆盖</p>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          所有结论都来自真实学习记录与对话证据。没有分数。
        </p>
      </section>

      <section className="border-t border-border pt-5">
        <p className="font-mono text-xs text-muted">{teacherName}记得这些</p>
        <div className="mt-3">
          {memories.length === 0 ? (
            <p className="text-sm leading-relaxed text-muted">
              还没有沉淀出稳定的记忆，持续学习后这里会记录{teacherName}对你的理解。
            </p>
          ) : (
            <MemoryList memories={memories} onChanged={onChanged} />
          )}
        </div>
      </section>

      <section className="grid gap-2 border-t border-border pt-5">
        <button
          type="button"
          className="rounded-[10px] bg-accent px-3 py-2 text-sm text-surface hover:bg-accent/85"
          onClick={onAskWhy}
        >
          问{teacherName}：为什么这样判断？
        </button>
        <button
          type="button"
          className="rounded-[10px] px-3 py-2 text-sm text-muted hover:bg-fg-soft hover:text-fg"
          onClick={onOpenArchive}
        >
          查看原始 AI 档案
        </button>
        <button
          type="button"
          data-testid="open-memories"
          className="rounded-[10px] px-3 py-2 text-sm text-muted hover:bg-fg-soft hover:text-fg"
          onClick={onManageMemories}
        >
          管理我的记忆 →
        </button>
      </section>
    </aside>
  )
}
