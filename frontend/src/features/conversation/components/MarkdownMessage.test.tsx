// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MarkdownMessage } from './MarkdownMessage'

describe('MarkdownMessage', () => {
  it('renders teacher bold text instead of exposing Markdown markers', () => {
    const { container } = render(
      <MarkdownMessage content="我是**霜铃**，一位耐心的老师。" />,
    )

    expect(container.textContent).toBe('我是霜铃，一位耐心的老师。')
    expect(container.querySelector('strong')?.textContent).toBe('霜铃')
    expect(container.textContent).not.toContain('**')
  })

  it('preserves line breaks and inline code', () => {
    const { container } = render(
      <MarkdownMessage content={'第一步：`print()`\n第二步：**观察结果**'} />,
    )

    expect(container.querySelector('br')).not.toBeNull()
    expect(container.querySelector('code')?.textContent).toBe('print()')
    expect(container.querySelector('strong')?.textContent).toBe('观察结果')
  })
})
