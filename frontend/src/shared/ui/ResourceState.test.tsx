// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResourceState } from './ResourceState'

afterEach(cleanup)

describe('ResourceState 状态视图', () => {
  it('loading 渲染标题与 status 角色', () => {
    render(<ResourceState type="loading" />)
    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText('正在加载')).toBeTruthy()
  })

  it('empty 可传入自定义动作', () => {
    render(<ResourceState type="empty" action={<button type="button">去选书</button>} />)
    expect(screen.getByRole('button', { name: '去选书' })).toBeTruthy()
  })

  it('error 显示标题/说明/requestId，重试按钮可用', () => {
    const onRetry = vi.fn()
    render(<ResourceState type="error" title="无法加载书库" description="请检查网络" requestId="req-9" onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByText('无法加载书库')).toBeTruthy()
    expect(screen.getByText('请求编号：req-9')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('提供 onRetry 时渲染可键盘触发的重试按钮', () => {
    render(<ResourceState type="error" onRetry={() => undefined} />)
    const button = screen.getByRole('button', { name: '重试' })
    expect(button.getAttribute('data-testid')).toBeNull()
    // 可聚焦（min-h 44px 点击区）
    expect((button as HTMLElement).className).toContain('min-h-[44px]')
  })
})
