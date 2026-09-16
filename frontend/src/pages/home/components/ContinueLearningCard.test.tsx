// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ContinueLearningCard } from './ContinueLearningCard'

vi.mock('@/features/companion', () => ({ useTeacherName: () => '温暖老师' }))

const book = { book_id: 'b1', title: 'AI 不是魔法', description: '入门' } as never
const chapter = {
  chapter_id: 'c2',
  book_id: 'b1',
  title: '训练数据',
  chapter_order: 2,
  summary: '本章讲训练数据。',
  estimated_minutes: 13,
  status: 'PUBLISHED',
} as never

afterEach(cleanup)

describe('ContinueLearningCard 四态主行动', () => {
  it('loading 显示恢复态', () => {
    render(<ContinueLearningCard loading error={false} progress={null} book={null} chapter={null} onContinue={() => undefined} onStart={() => undefined} onChat={() => undefined} />)
    expect(screen.getByTestId('continue-loading')).toBeTruthy()
  })

  it('进度加载失败显示错误而非"没有读过"', () => {
    render(<ContinueLearningCard loading={false} error progress={null} book={null} chapter={null} onContinue={() => undefined} onStart={() => undefined} onChat={() => undefined} />)
    expect(screen.getByTestId('continue-error')).toBeTruthy()
    expect(screen.queryByText('还没有开始学习')).toBeNull()
    expect(screen.queryByText(/暂时无法读取上次进度/)).toBeTruthy()
  })

  it('新用户显示"选一门适合你的课程"', () => {
    render(<ContinueLearningCard loading={false} error={false} progress={null} book={null} chapter={null} onContinue={() => undefined} onStart={() => undefined} onChat={() => undefined} />)
    expect(screen.getByTestId('continue-empty')).toBeTruthy()
    expect(screen.getByText('选一门适合你的课程')).toBeTruthy()
  })

  it('进行中：唯一主行动为"继续第 N 章"，点击回调', () => {
    const onContinue = vi.fn()
    render(<ContinueLearningCard loading={false} error={false} progress={{ status: 'READING', position_percent: 55, book_id: 'b1', chapter_id: 'c2' } as never} book={book} chapter={chapter} onContinue={onContinue} onStart={() => undefined} onChat={() => undefined} />)
    const action = screen.getByTestId('continue-learning-action')
    expect(action.textContent).toBe('继续第 2 章 →')
    fireEvent.click(action)
    expect(onContinue).toHaveBeenCalledOnce()
  })

  it('已完成：主行动改为"继续下一章"', () => {
    render(<ContinueLearningCard loading={false} error={false} progress={{ status: 'COMPLETED', position_percent: 100, book_id: 'b1', chapter_id: 'c2' } as never} book={book} chapter={chapter} onContinue={() => undefined} onStart={() => undefined} onChat={() => undefined} />)
    expect(screen.getByText(/上一章已完成/)).toBeTruthy()
    expect(screen.getByTestId('continue-learning-action').textContent).toBe('继续下一章 →')
  })
})
