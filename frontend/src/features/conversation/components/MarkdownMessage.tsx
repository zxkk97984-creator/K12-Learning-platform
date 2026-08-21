import { Fragment, type ReactNode } from 'react'

const INLINE_MARKDOWN = /(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+`|\*[^*\n]+?\*|_[^_\n]+?_)/g

function renderInline(line: string, lineIndex: number): ReactNode[] {
  const nodes: ReactNode[] = []
  let lastIndex = 0

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

/** Render the small, safe Markdown subset used by teacher messages. */
export function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split(/\r?\n/)
  return (
    <>
      {lines.map((line, index) => (
        <Fragment key={`line-${index}`}>
          {index > 0 ? <br /> : null}
          {renderInline(line, index)}
        </Fragment>
      ))}
    </>
  )
}
