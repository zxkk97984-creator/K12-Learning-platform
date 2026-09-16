import { useCallback, useState } from 'react'

import type { Chapter } from '@/entities/book/types'
import type { ChapterCompletionResult } from '@/shared/api/learning-service'

interface ChapterCompletionCardProps {
  /** 本书全部已发布章节（按 chapter_order 升序），用于找"下一章"。 */
  chapters: Chapter[]
  /** 当前章节的 chapter_id。 */
  chapterId: string
  chapterTitle: string
  /** 当前章节是否已在事实表中完成（来自目录/详情 DTO 的 is_completed）。 */
  alreadyCompleted: boolean
  /** 提交"完成本章"的后端调用；内部负责 pending/error 状态。 */
  onSubmit: () => Promise<ChapterCompletionResult>
  /** 进入指定章节（下一章）。 */
  onNavigateNext: (chapterId: string) => void
  /** 发起练习（给我出题）。 */
  onPractice: () => void
}

type CardState = 'idle' | 'submitting' | 'done' | 'error'

function findNextChapter(
  chapters: Chapter[],
  chapterId: string,
): Chapter | undefined {
  const sorted = [...chapters].sort((a, b) => a.chapter_order - b.chapter_order)
  const index = sorted.findIndex((item) => item.chapter_id === chapterId)
  if (index < 0) return undefined
  return sorted[index + 1]
}

/** 一章末尾的"完成—下一章/练习"操作区（T13c）。
 *
 * 只认显式按钮：滚动到章节末尾 / 触发 CHAPTER_FINISHED 事件不会把本章标记为
 * "完成"（F07 口径）。状态在组件内收敛，失败保留重试。
 */
export function ChapterCompletionCard({
  chapters,
  chapterId,
  chapterTitle,
  alreadyCompleted,
  onSubmit,
  onNavigateNext,
  onPractice,
}: ChapterCompletionCardProps) {
  const [state, setState] = useState<CardState>(alreadyCompleted ? 'done' : 'idle')
  const [result, setResult] = useState<ChapterCompletionResult | null>(null)

  const nextChapter = findNextChapter(chapters, chapterId)

  const submit = useCallback(async () => {
    setState('submitting')
    try {
      const completion = await onSubmit()
      setResult(completion)
      setState('done')
    } catch {
      setState('error')
    }
  }, [onSubmit])

  if (state === 'submitting') {
    return (
      <div className="rounded-[14px] border border-border bg-surface p-4 text-sm text-muted">
        正在记录本章完成…
      </div>
    )
  }

  if (state === 'done') {
    const bookCompleted = result?.book_completed ?? false
    const heading = bookCompleted ? '恭喜，整本书已学完！' : `「${chapterTitle}」已完成`
    return (
      <div className="rounded-[14px] border border-border bg-surface p-4">
        <p className="font-display text-lg text-fg">{heading}</p>
        {result ? (
          <p className="mt-1 text-xs text-muted">
            完成 {result.completed_chapters} / {result.published_chapters} 个章节
          </p>
        ) : null}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {nextChapter ? (
            <button
              type="button"
              className="rounded-[10px] bg-accent px-3 py-2 text-xs text-surface hover:bg-accent/85"
              onClick={() => onNavigateNext(nextChapter.chapter_id)}
            >
              下一章：{nextChapter.title} →
            </button>
          ) : (
            <button
              type="button"
              className="rounded-[10px] bg-accent px-3 py-2 text-xs text-surface hover:bg-accent/85"
              onClick={onPractice}
            >
              再练一题巩固
            </button>
          )}
          <button
            type="button"
            className="rounded-[10px] border border-border bg-surface px-3 py-2 text-xs text-fg hover:border-fg"
            onClick={onPractice}
          >
            给我出题
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-[14px] border border-border bg-surface p-4">
      <p className="text-sm text-fg">
        读到这里了吗？{chapterTitle}读完点一下，让{'‘'}完成{'’'}记录你真实的进度。
      </p>
      {state === 'error' ? (
        <p className="mt-2 text-xs text-destructive">完成后记录保存失败，请重试。</p>
      ) : null}
      <button
        type="button"
        className="mt-4 rounded-[10px] bg-accent px-3 py-2 text-xs text-surface hover:bg-accent/85"
        onClick={() => void submit()}
      >
        {alreadyCompleted ? '已完成，查看结果' : '完成本章'}
      </button>
    </div>
  )
}
