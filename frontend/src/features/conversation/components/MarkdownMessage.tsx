import { Fragment, type ReactNode } from 'react'

const INLINE_MARKDOWN = /(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+`|\*[^*\n]+?\*|_[^_\n]+?_)/g
const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g

/** 只允许 http/https 链接，拒绝 javascript:/data: 等（T19 §安全）。 */
function isSafeHref(href: string): boolean {
  return /^https?:\/\//i.test(href)
}

function renderInline(line: string, lineIndex: number): ReactNode[] {
  const nodes: ReactNode[] = []
  let lastIndex = 0
  // 先扫安全链接，未命中再回退到内联加粗/代码。链接内文本不再重复解析标记。
  let matchedLink = false
  for (const match of line.matchAll(LINK_RE)) {
    matchedLink = true
    const token = match[0]
    const start = match.index ?? 0
    const label = match[1]
    const href = match[2]
    if (start > lastIndex) nodes.push(...renderInline(line.slice(lastIndex, start), lineIndex))
    if (isSafeHref(href)) {
      nodes.push(
        <a
          key={`${lineIndex}-${start}`}
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          className="text-accent underline"
        >
          {label}
        </a>,
      )
    } else {
      nodes.push(<Fragment key={`${lineIndex}-${start}`}>{label}</Fragment>)
    }
    lastIndex = start + token.length
  }
  if (matchedLink) {
    if (lastIndex < line.length) nodes.push(...renderInline(line.slice(lastIndex), lineIndex))
    return nodes
  }

  for (const match of line.matchAll(INLINE_MARKDOWN)) {
    const token = match[0]
    const start = match.index ?? 0
    if (start > lastIndex) nodes.push(line.slice(lastIndex, start))

    if (token.startsWith('**') || token.startsWith('__')) {
      nodes.push(
        <strong key={`${lineIndex}-${start}`} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      nodes.push(
        <code
          key={`${lineIndex}-${start}`}
          className="rounded bg-fg-soft px-1 font-mono text-[0.92em]"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      nodes.push(<em key={`${lineIndex}-${start}`}>{token.slice(1, -1)}</em>)
    }
    lastIndex = start + token.length
  }

  if (lastIndex < line.length) nodes.push(line.slice(lastIndex))
  return nodes
}

interface Block {
  kind: 'paragraph' | 'code'
  lines: string[]
}

function toBlocks(content: string): Block[] {
  const blocks: Block[] = []
  const rawLines = content.split(/\r?\n/)
  let i = 0
  while (i < rawLines.length) {
    const line = rawLines[i]
    const fence = line.match(/^```(\w*)\s*$/)
    if (fence) {
      const codeLines: string[] = []
      i += 1
      while (i < rawLines.length && !/^```\s*$/.test(rawLines[i])) {
        codeLines.push(rawLines[i])
        i += 1
      }
      i += 1 // 跳过结束围栏
      blocks.push({ kind: 'code', lines: codeLines })
    } else {
      const para: string[] = []
      while (i < rawLines.length && !/^```/.test(rawLines[i])) {
        para.push(rawLines[i])
        i += 1
      }
      blocks.push({ kind: 'paragraph', lines: para })
    }
  }
  return blocks
}

function isListItem(line: string): boolean {
  return /^(\s*)([-*+]|\d+[.)])\s+/.test(line)
}

function renderListLine(line: string, index: number): ReactNode {
  const ordered = line.match(/^(\s*)\d+[.)]\s+(.*)$/)
  const unordered = line.match(/^(\s*)[-*+]\s+(.*)$/)
  if (ordered) {
    return (
      <li key={index} style={{ listStyle: 'decimal', marginLeft: '1.1em' }}>
        {renderInline(ordered[2], index)}
      </li>
    )
  }
  if (unordered) {
    return (
      <li key={index} style={{ listStyle: 'disc', marginLeft: '1.1em' }}>
        {renderInline(unordered[2], index)}
      </li>
    )
  }
  return <Fragment key={index}>{renderInline(line, index)}</Fragment>
}

function renderParagraph(lines: string[], keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const buffer: string[] = []
  const flush = (key: string) => {
    if (buffer.length === 0) return
    nodes.push(
      <ul key={key} className="my-1 pl-0">
        {buffer.map((line, idx) => renderListLine(line, idx))}
      </ul>,
    )
    buffer.length = 0
  }
  let blockIndex = 0
  lines.forEach((line, index) => {
    if (line.trim() === '') {
      flush(`${keyBase}-${blockIndex++}`)
      return
    }
    if (isListItem(line)) {
      buffer.push(line)
    } else {
      flush(`${keyBase}-${blockIndex++}`)
      const text = renderInline(line, index)
      nodes.push(<Fragment key={`${keyBase}-t-${index}`}>{text}</Fragment>)
      // 段内换行
      if (index < lines.length - 1) nodes.push(<br key={`${keyBase}-br-${index}`} />)
    }
  })
  flush(`${keyBase}-${blockIndex}`)
  return nodes
}

/** 渲染教师消息的安全 Markdown 子集：段落/有序无序列表/围栏代码块/安全链接。
 *
 * 安全策略（T19）：不引入 dangerouslySetInnerHTML；HTML 一律按纯文本处理（React 自动转义，
 * 原始 HTML 不执行）；链接仅校验 http/https，其余（javascript:/data:）按纯文本显示。
 * 选择手写安全子集而非引入解析库，理由：需求仅段落/列表/代码/链接四类，自足子集不含
 * 任一「执行 HTML」路径，避免为极小需求引入重量依赖与受攻击面。
 */
export function MarkdownMessage({ content }: { content: string }) {
  const blocks = toBlocks(content)
  return (
    <>
      {blocks.map((block, bIndex) => {
        if (block.kind === 'code') {
          return (
            <pre
              key={`code-${bIndex}`}
              className="my-1 overflow-x-auto rounded-lg bg-fg-soft p-2 font-mono text-[12px] leading-relaxed text-fg"
            >
              {block.lines.join('\n')}
            </pre>
          )
        }
        return <Fragment key={`p-${bIndex}`}>{renderParagraph(block.lines, `p-${bIndex}`)}</Fragment>
      })}
    </>
  )
}
