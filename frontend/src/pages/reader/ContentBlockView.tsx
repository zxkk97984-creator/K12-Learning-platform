import { useState } from 'react'

import type { ContentBlock, ContentBlockType } from '@/entities/book/types'
import { useTeacherName } from '@/features/companion'

/** 拆分标记文本：同一术语出现多次时不截断后文（修复 split() 只留首段之前的问题）。 */
export function renderMarkedText(text: unknown, mark: unknown) {
  if (typeof text !== 'string') return null
  if (typeof mark !== 'string' || !mark || !text.includes(mark)) return text
  // splitAll：所有出现处都标出来，保留标记之间的正文。
  const parts = text.split(mark)
  return (
    <>
      {parts.map((part, index) => (
        <span key={index}>
          {part}
          {index < parts.length - 1 ? (
            <mark className="rounded bg-accent-soft px-1 text-fg">{mark}</mark>
          ) : null}
        </span>
      ))}
    </>
  )
}

function exampleOf(content: Record<string, unknown>): { label: string; text: string } | null {
  const example = content.example
  if (!example || typeof example !== 'object') return null
  const record = example as Record<string, unknown>
  if (typeof record.label !== 'string' || typeof record.text !== 'string') return null
  return { label: record.label, text: record.text }
}

interface ContentBlockViewProps {
  block: ContentBlock
  onExplain: () => void
  /**
   * 未知内容类型上报：不静默吞掉（T11）。默认上报到 console，便于上层接入监控。
   */
  onUnknownBlockType?: (blockType: string, blockId: string) => void
}

/**
 * 阅读正文内容块视图（从 ReaderPage 提取，便于单测）。
 * 覆盖 TITLE/PARAGRAPH/KNOWLEDGE_CARD/EXAMPLE/CALLOUT/FIGURE/IMAGE；
 * 未知类型显式反馈并上报，不静默 return null。
 */
export function ContentBlockView({ block, onExplain, onUnknownBlockType }: ContentBlockViewProps) {
  const sectionKey = block.section_key ?? undefined
  const teacherName = useTeacherName()

  if (block.block_type === 'TITLE') {
    return (
      <h2 data-read-section={sectionKey} className="font-display text-2xl text-fg">
        {typeof block.content.text === 'string' ? block.content.text : ''}
      </h2>
    )
  }

  if (block.block_type === 'PARAGRAPH' || block.block_type === 'HIGHLIGHT') {
    return (
      <p data-read-section={sectionKey} className="mb-4 text-[18px] leading-[1.85] text-fg">
        {renderMarkedText(block.content.text, block.content.mark)}
      </p>
    )
  }

  if (block.block_type === 'KNOWLEDGE_CARD') {
    const title = typeof block.content.title === 'string' ? block.content.title : ''
    const text = typeof block.content.text === 'string' ? block.content.text : ''
    const example = exampleOf(block.content)
    return (
      <article
        data-read-section={sectionKey}
        data-kc-block={block.block_id}
        data-kp-ids={(block.knowledge_point_ids ?? []).join(',')}
        className="my-6 border-y border-border bg-surface px-6 py-5"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="font-mono text-xs tracking-wider text-muted">知识卡片</span>
            <h3 className="font-display text-xl text-fg">{title}</h3>
          </div>
          <button
            type="button"
            className="rounded-[10px] border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-fg"
            onClick={onExplain}
          >
            让{teacherName}讲给我听
          </button>
        </div>
        <p className="mt-3 text-[16px] leading-relaxed text-muted">{text}</p>
        {example ? (
          <div className="mt-4 border-l-2 border-fg bg-fg-soft px-4 py-3">
            <strong className="block text-sm text-fg">{example.label}</strong>
            <span className="mt-1 block text-[15px] text-muted">{example.text}</span>
          </div>
        ) : null}
      </article>
    )
  }

  if (block.block_type === 'EXAMPLE') {
    const text = typeof block.content.text === 'string' ? block.content.text : ''
    return (
      <div data-read-section={sectionKey} className="my-5 border-l-2 border-fg bg-fg-soft px-4 py-3">
        <strong className="block text-sm text-fg">生活里的例子</strong>
        <span className="mt-1 block text-[15px] text-muted">{text}</span>
      </div>
    )
  }

  if (block.block_type === 'CALLOUT') {
    const title = typeof block.content.title === 'string' ? block.content.title : ''
    const text = typeof block.content.text === 'string' ? block.content.text : ''
    return (
      <aside data-read-section={sectionKey} className="my-6 border-l-2 border-fg bg-surface px-5 py-4">
        <strong className="font-display text-lg text-fg">{title}</strong>
        <p className="mt-2 text-[16px] leading-relaxed text-muted">{text}</p>
      </aside>
    )
  }

  if (block.block_type === 'FIGURE' || block.block_type === 'IMAGE') {
    return <FigureView block={block} sectionKey={sectionKey} />
  }

  // 未知/将来新增的内容块类型：明确反馈 + 上报，不静默吞掉。
  onUnknownBlockType?.(block.block_type as string, block.block_id)
  return (
    <div
      data-read-section={sectionKey}
      role="note"
      className="my-4 rounded-lg border border-dashed border-border bg-surface px-4 py-3 text-sm text-muted"
    >
      暂不支持的内容类型（{String(block.block_type)}）。
    </div>
  )
}

function FigureView({ block, sectionKey }: { block: ContentBlock; sectionKey?: string }) {
  const src = typeof block.content.src === 'string' ? block.content.src : ''
  const alt = typeof block.content.alt === 'string' ? block.content.alt : ''
  const caption = typeof block.content.caption === 'string' ? block.content.caption : ''
  const [failed, setFailed] = useState(false)

  if (!src) {
    // 无实图：明确"暂无图解"（等价文字来自 alt），不伪造图。
    return (
      <figure data-read-section={sectionKey} className="my-6">
        <div
          role="img"
          aria-label={alt || '图解'}
          className="grid min-h-[96px] place-items-center rounded-lg border border-border bg-fg-soft px-4 py-6 text-center text-muted"
        >
          <div>
            <span className="text-sm">暂无图解</span>
            {alt ? <p className="mt-2 text-sm leading-relaxed">{alt}</p> : null}
          </div>
        </div>
        {caption ? (
          <figcaption className="mt-2 text-xs text-muted">{caption}</figcaption>
        ) : null}
      </figure>
    )
  }

  if (failed) {
    return (
      <figure data-read-section={sectionKey} className="my-6">
        <div className="grid min-h-[96px] place-items-center rounded-lg border border-border bg-fg-soft px-4 py-6 text-center">
          <div>
            <p className="text-sm text-fg">图解暂时无法加载</p>
            {alt ? <p className="mt-2 text-sm leading-relaxed text-muted">{alt}</p> : null}
            <button
              type="button"
              className="mt-3 rounded-[10px] border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-fg"
              onClick={() => setFailed(false)}
            >
              重试
            </button>
          </div>
        </div>
        {caption ? (
          <figcaption className="mt-2 text-xs text-muted">{caption}</figcaption>
        ) : null}
      </figure>
    )
  }

  return (
    <figure data-read-section={sectionKey} className="my-6">
      <img
        src={src}
        alt={alt || caption || '图解'}
        loading="lazy"
        onError={() => setFailed(true)}
        className="mx-auto block max-w-full rounded-lg"
      />
      {caption ? (
        <figcaption className="mt-2 text-center text-xs text-muted">{caption}</figcaption>
      ) : null}
    </figure>
  )
}

export const CONTENT_BLOCK_TYPES: ContentBlockType[] = [
  'TITLE',
  'PARAGRAPH',
  'IMAGE',
  'FIGURE',
  'KNOWLEDGE_CARD',
  'EXAMPLE',
  'CALLOUT',
  'HIGHLIGHT',
]
