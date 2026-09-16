// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { CodeOutputPanel } from './CodeOutputPanel'
import type { CodeRun } from '@/shared/api'

function makeRun(overrides: Partial<CodeRun> = {}): CodeRun {
  return {
    run_id: 'run-1',
    task_id: 'task-1',
    status: 'SUCCESS',
    outputs: [],
    execution_time_ms: 120,
    exit_code: 0,
    error: null,
    created_at: '2026-09-16T00:00:00Z',
    ...overrides,
  }
}

describe('CodeOutputPanel', () => {
  it('提示先运行', () => {
    render(<CodeOutputPanel run={null} />)
    expect(screen.getByText(/点击「运行」/)).toBeTruthy()
  })

  it('区分渲染 stdout 与 stderr', () => {
    const run = makeRun({
      outputs: [
        { msg_type: 'stream', content: { name: 'stdout', text: '正常输出' } },
        { msg_type: 'stream', content: { name: 'stderr', text: '错误输出' } },
      ],
    })
    render(<CodeOutputPanel run={run} />)
    expect(screen.getByTestId('codelab-output-stdout').textContent).toContain('正常输出')
    expect(screen.getByTestId('codelab-output-stderr').textContent).toContain('错误输出')
  })

  it('渲染 traceback 类型的 error 输出', () => {
    const run = makeRun({
      status: 'FAILED',
      exit_code: 1,
      outputs: [{ msg_type: 'error', content: { text: 'Traceback: ValueError' } }],
    })
    render(<CodeOutputPanel run={run} />)
    expect(screen.getByTestId('codelab-output-error').textContent).toContain('Traceback')
    expect(screen.getByText('运行出错')).toBeTruthy()
  })

  it('渲染 base64 PNG 图片输出', () => {
    const run = makeRun({
      outputs: [
        { msg_type: 'display_data', content: { data: { 'image/png': 'aGVsbG8=' } } },
      ],
    })
    render(<CodeOutputPanel run={run} />)
    const img = screen.getByAltText('程序输出的图表') as HTMLImageElement
    expect(img.src).toBe('data:image/png;base64,aGVsbG8=')
  })

  it('display_data 的 text/plain 走文本分支而不是 JSON.stringify（dai 的缺陷修复点）', () => {
    const run = makeRun({
      outputs: [
        { msg_type: 'execute_result', content: { data: { 'text/plain': '42' } } },
      ],
    })
    render(<CodeOutputPanel run={run} />)
    const result = screen.getByTestId('codelab-output-result')
    expect(result.textContent).toBe('42')
    // 关键：不能出现 JSON 包裹
    expect(result.textContent).not.toContain('{')
    expect(screen.queryByTestId('codelab-output-raw')).toBeNull()
  })

  it('未知结构才回退到原始 JSON', () => {
    // 故意构造契约之外的形状，验证兜底分支
    const run = makeRun({ outputs: [{ msg_type: 'weird', content: { foo: 'bar' } as never }] })
    render(<CodeOutputPanel run={run} />)
    expect(screen.getByTestId('codelab-output-raw').textContent).toContain('foo')
  })

  it('显示耗时与退出码', () => {
    render(<CodeOutputPanel run={makeRun()} />)
    expect(screen.getByText(/耗时 120 ms/)).toBeTruthy()
    expect(screen.getByText(/退出码 0/)).toBeTruthy()
  })

  it('超时状态有明确文案', () => {
    render(<CodeOutputPanel run={makeRun({ status: 'TIMEOUT', outputs: [], execution_time_ms: 9000 })} />)
    expect(screen.getByText('运行超时')).toBeTruthy()
  })
})

afterEach(cleanup)
