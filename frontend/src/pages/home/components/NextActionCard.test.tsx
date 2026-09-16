// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { LearningNextAction } from '@/shared/api/recommendation-service'
import { NextActionCard } from './NextActionCard'

afterEach(cleanup)

function action(overrides: Partial<LearningNextAction> = {}): LearningNextAction {
  return {
    type: 'NEXT_CHAPTER',
    label: '学下一章：第二章',
    book_id: 'book-1',
    chapter_id: 'chapter-2',
    quiz_session_id: null,
    reason: '你已经读完上一章，接着学《第二章》衔接自然。',
    evidence_ids: ['chapter-2'],
    ...overrides,
  }
}

describe('NextActionCard（T16 §6.1）', () => {
  it('渲染行动标签与理由并回调 onOpen', () => {
    const onOpen = vi.fn()
    render(<NextActionCard action={action()} loading={false} onOpen={onOpen} />)
    expect(screen.getByText('学下一章：第二章')).toBeTruthy()
    expect(screen.getByText(/读完上一章/)).toBeTruthy()
    fireEvent.click(screen.getByText('去做 →'))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ type: 'NEXT_CHAPTER' }))
  })

  it('loading 时显示计算中，不渲染行动按钮', () => {
    const onOpen = vi.fn()
    render(<NextActionCard loading onOpen={onOpen} />)
    expect(screen.getByText('正在计算下一步…')).toBeTruthy()
    expect(screen.queryByText('去做 →')).toBeNull()
  })

  it('REVIEW_QUIZ 显示"去回顾"并提供暂时跳过', () => {
    const onOpen = vi.fn()
    const onSkip = vi.fn()
    render(
      <NextActionCard
        action={action({ type: 'REVIEW_QUIZ', quiz_session_id: 'quiz-9' })}
        loading={false}
        onOpen={onOpen}
        onSkip={onSkip}
      />,
    )
    fireEvent.click(screen.getByText('去回顾 →'))
    expect(onOpen).toHaveBeenCalled()
    fireEvent.click(screen.getByText('暂时跳过'))
    expect(onSkip).toHaveBeenCalled()
  })
})
