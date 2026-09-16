// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ContentBlockView, renderMarkedText } from './ContentBlockView'

vi.mock('@/features/companion', () => ({ useTeacherName: () => '温暖老师' }))

afterEach(cleanup)

function block(overrides: Record<string, unknown>) {
  return {
    block_id: 'b-1',
    chapter_id: 'c-1',
    block_type: 'PARAGRAPH',
    content: {},
    block_order: 1,
    section_key: null,
    knowledge_point_ids: [],
    ...overrides,
  } as never
}

describe('渲染标记文本（同一术语多次出现）', () => {
  it('第二次出现之后的正文不被截断', () => {
    const { container } = render(<div>{renderMarkedText('训练数据让模型学习，训练数据很重要。', '训练数据')}</div>)
    expect(container.textContent).toBe('训练数据让模型学习，训练数据很重要。')
    expect(container.querySelectorAll('mark')).toHaveLength(2)
  })
})

describe('ContentBlockView', () => {
  it('FIGURE 有 src 时渲染真实图且 alt 正确', () => {
    render(
      <ContentBlockView
        block={block({ block_type: 'FIGURE', content: { src: '/api/v1/library-assets/x/flow.svg', alt: '训练流程', caption: '图注' } })}
        onExplain={() => undefined}
      />,
    )
    const img = screen.getByRole('img')
    expect(img.getAttribute('src')).toBe('/api/v1/library-assets/x/flow.svg')
    expect(img.getAttribute('alt')).toBe('训练流程')
    expect(screen.getByText('图注')).toBeTruthy()
  })

  it('FIGURE 无 src 显示"暂无图解"等价文字，不伪造图', () => {
    render(
      <ContentBlockView
        block={block({ block_type: 'FIGURE', content: { alt: '监督学习示意图', caption: '图注' } })}
        onExplain={() => undefined}
      />,
    )
    expect(screen.getByText('暂无图解')).toBeTruthy()
    expect(screen.getByText('监督学习示意图')).toBeTruthy()
    expect(screen.queryByRole('img')).toBeTruthy() // role=img 容器承载等价文字
  })

  it('IMAGE 渲染 img，加载失败可重试（后文仍完整）', () => {
    render(
      <ContentBlockView
        block={block({ block_type: 'IMAGE', content: { src: '/bad.svg', alt: '测试图' } })}
        onExplain={() => undefined}
      />,
    )
    const img = screen.getByRole('img')
    fireEvent.error(img)
    expect(screen.getByText('图解暂时无法加载')).toBeTruthy()
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
  })

  it('未知内容类型显示明确反馈并上报', () => {
    const onUnknown = vi.fn()
    render(
      <ContentBlockView
        block={block({ block_type: 'WIDGET' })}
        onExplain={() => undefined}
        onUnknownBlockType={onUnknown}
      />,
    )
    expect(onUnknown).toHaveBeenCalledWith('WIDGET', 'b-1')
    expect(screen.getByText(/暂不支持的内容类型/)).toBeTruthy()
  })

  it('PARAGRAPH 正文按 18px 输出（阅读正文可读性）', () => {
    render(
      <ContentBlockView
        block={block({ block_type: 'PARAGRAPH', content: { text: '一段正文' } })}
        onExplain={() => undefined}
      />,
    )
    const p = screen.getByText('一段正文')
    expect(p.className).toContain('text-[18px]')
  })
})
