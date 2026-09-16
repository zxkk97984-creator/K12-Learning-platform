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

  it('renders ordered and unordered lists as list items (T19)', () => {
    const { container } = render(
      <MarkdownMessage content={'要点：\n- 第一条\n- 第二条\n\n步骤：\n1. 第一步\n2. 第二步'} />,
    )
    const items = container.querySelectorAll('li')
    expect(items.length).toBeGreaterThanOrEqual(4)
    expect(container.textContent).toContain('第一条')
    expect(container.textContent).toContain('第二步')
  })

  it('renders fenced code blocks as monospace pre, not executing anything', () => {
    const { container } = render(
      <MarkdownMessage content={'示例：\n```python\nprint("hi")\n```'} />,
    )
    const pre = container.querySelector('pre')
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain('print("hi")')
  })

  it('renders safe http/https links with target blank + rel', () => {
    const { container } = render(
      <MarkdownMessage content={'参考 [训练数据手册](https://example.com/doc)'} />,
    )
    const link = container.querySelector('a')
    expect(link?.getAttribute('href')).toBe('https://example.com/doc')
    expect(link?.getAttribute('rel')).toContain('noopener')
  })

  it('does not execute javascript: links (treated as plain text)', () => {
    const { container } = render(
      <MarkdownMessage content={'点[这里](javascript:alert(1))看看'} />,
    )
    const link = container.querySelector('a')
    expect(link).toBeNull()
    expect(container.textContent).toContain('这里')
    expect(container.textContent).toContain('javascript:alert(1)')
  })

  it('raw HTML is escaped and not executed (T19 security)', () => {
    const { container } = render(
      <MarkdownMessage content={'<script>alert(1)</script> <b>加粗不是标签</b>'} />,
    )
    // React 转义：script 标签不产生 script 元素，b 标签按纯文本显示。
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toContain('<script>alert(1)</script>')
    expect(container.textContent).toContain('<b>加粗不是标签</b>')
  })
})
