import { useCallback, useEffect, useState } from 'react'

import type { StudentMemory } from '@/entities/memory/types'
import { MemoryList } from '@/features/memory'
import { memoryService } from '@/mocks/services'

export default function MemoriesPage() {
  const [memories, setMemories] = useState<StudentMemory[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setMemories(await memoryService.getMemories())
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section className="py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">成长 · 记忆管理</p>
      <h1 className="mt-3 font-display text-4xl text-fg">AI 记得什么</h1>
      <p className="mt-2 max-w-[52ch] text-sm text-muted">
        霜铃对你的每条理解都来自真实学习记录。你可以确认、修改或忘记。
      </p>
      {loading ? (
        <p className="py-8 text-center text-sm text-muted">正在加载记忆…</p>
      ) : (
        <div className="mt-6 max-w-2xl">
          <MemoryList memories={memories} onChanged={() => void load()} />
        </div>
      )}
    </section>
  )
}
