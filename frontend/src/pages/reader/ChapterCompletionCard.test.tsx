// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Chapter } from '@/entities/book/types'
import type { ChapterCompletionResult } from '@/shared/api/learning-service'
import { ChapterCompletionCard } from './ChapterCompletionCard'

afterEach(cleanup)

function chapter(order: number, id: string, title: string): Chapter {
  return { chapter_id: id, book_id: 'b-1', title, chapter_order: order, summary: null, estimated_minutes: 10, status: 'PUBLISHED' }
}

function completion(overrides: Partial<ChapterCompletionResult> = {}): ChapterCompletionResult {
  return {
    chapter_id: 'c2',
    book_id: 'b-1',
    completed_at: '2026-09-07T08:00:00Z',
    source: 'EXPLICIT',
    book_completed: false,
    completed_chapters: 2,
    published_chapters: 3,
    ...overrides,
  }
}

describe('ChapterCompletionCard', () => {
  it('默认显示"完成本章"，不因滚动末端自动完成（F07 语义）', () => {
    render(
      <ChapterCompletionCard
        chapters={[]}
        chapterId="c2"
        chapterTitle="第二章"
        alreadyCompleted={false}
        onSubmit={async () => completion()}
        onNavigateNext={() => undefined}
        onPractice={() => undefined}
      />,
    )
    expect(screen.getByText('完成本章')).toBeTruthy()
    expect(screen.queryByText('下一章')).toBeNull()
  })

  it('点击提交后进入 pending，再展示完成结果', async () => {
    let resolveFn!: (v: ChapterCompletionResult) => void
    const promise = new Promise<ChapterCompletionResult>((resolve) => {
      resolveFn = resolve
    })
    render(
      <ChapterCompletionCard
        chapters={[chapter(1, 'c1', '第一章'), chapter(2, 'c2', '第二章')]}
        chapterId="c2"
        chapterTitle="第二章"
        alreadyCompleted={false}
        onSubmit={() => promise}
        onNavigateNext={() => undefined}
        onPractice={() => undefined}
      />,
    )
    fireEvent.click(screen.getByText('完成本章'))
    expect(screen.getByText(/正在记录/)).toBeTruthy()
    resolveFn(completion())
    await waitFor(() => expect(screen.getByText('「第二章」已完成')).toBeTruthy())
  })

  it('整书完成时提示"整本书已学完"并提供下一章', () => {
    render(
      <ChapterCompletionCard
        chapters={[chapter(1, 'c1', '第一章'), chapter(2, 'c2', '第二章'), chapter(3, 'c3', '第三章')]}
        chapterId="c2"
        chapterTitle="第二章"
        alreadyCompleted={false}
        onSubmit={async () => completion({ book_completed: true, completed_chapters: 3, published_chapters: 3 })}
        onNavigateNext={() => undefined}
        onPractice={() => undefined}
      />,
    )
    fireEvent.click(screen.getByText('完成本章'))
    return waitFor(() => expect(screen.getByText('恭喜，整本书已学完！')).toBeTruthy())
  })

  it('最后一个章节完成时显示"再练一题"而非下一章', () => {
    render(
      <ChapterCompletionCard
        chapters={[chapter(1, 'c1', '第一章'), chapter(2, 'c2', '第二章')]}
        chapterId="c2"
        chapterTitle="第二章"
        alreadyCompleted={false}
        onSubmit={async () => completion()}
        onNavigateNext={() => undefined}
        onPractice={() => undefined}
      />,
    )
    fireEvent.click(screen.getByText('完成本章'))
    return waitFor(() => {
      expect(screen.queryByText(/下一章/)).toBeNull()
      expect(screen.getByText('再练一题巩固')).toBeTruthy()
    })
  })

  it('提交失败保留重试', async () => {
    render(
      <ChapterCompletionCard
        chapters={[]}
        chapterId="c2"
        chapterTitle="第二章"
        alreadyCompleted={false}
        onSubmit={async () => {
          throw new Error('boom')
        }}
        onNavigateNext={() => undefined}
        onPractice={() => undefined}
      />,
    )
    fireEvent.click(screen.getByText('完成本章'))
    await waitFor(() => expect(screen.getByText(/保存失败/)).toBeTruthy())
    expect(screen.getByText('完成本章')).toBeTruthy()
  })

  it('alreadyCompleted 时展示结果态，点击查看结果', async () => {
    render(
      <ChapterCompletionCard
        chapters={[chapter(1, 'c1', '第一章'), chapter(2, 'c2', '第二章')]}
        chapterId="c2"
        chapterTitle="第二章"
        alreadyCompleted={true}
        onSubmit={async () => completion()}
        onNavigateNext={() => undefined}
        onPractice={() => undefined}
      />,
    )
    expect(screen.getByText('「第二章」已完成')).toBeTruthy()
  })

  it('提供下一章导航回调', async () => {
    const onNavigateNext = vi.fn()
    render(
      <ChapterCompletionCard
        chapters={[chapter(1, 'c1', '第一章'), chapter(2, 'c2', '第二章')]}
        chapterId="c1"
        chapterTitle="第一章"
        alreadyCompleted={false}
        onSubmit={async () => completion()}
        onNavigateNext={onNavigateNext}
        onPractice={() => undefined}
      />,
    )
    fireEvent.click(screen.getByText('完成本章'))
    await waitFor(() => expect(screen.getByText(/下一章：第二章/)).toBeTruthy())
    fireEvent.click(screen.getByText(/下一章：第二章/))
    expect(onNavigateNext).toHaveBeenCalledWith('c2')
  })
})
