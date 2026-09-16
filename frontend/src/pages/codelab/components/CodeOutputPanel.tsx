import type { CodeOutput, CodeRun } from '@/shared/api'

/**
 * 沙箱输出渲染。
 *
 * 契约沿用 dai / Jupyter IOPub 的 `{msg_type, content}` 形状，但**渲染是重写的**。
 * dai 没有共用渲染器（四处重复实现），且 `CodeCell.vue:178-185` 在常见情形下是错的：
 * `execute_result` / `display_data` 里带 `text/plain` 的条目会落到
 * `JSON.stringify(output)` 分支、把结果打成 JSON 字符串。这里显式处理
 * `text/plain`，并把 stdout 与 stderr 分开显示（dai 的 sample-run 在服务端就把
 * 两者拼成了一个字符串，前端无从区分）。
 */

function isImage(output: CodeOutput): string | null {
  const png = output.content?.data?.['image/png']
  return typeof png === 'string' && png.length > 0 ? png : null
}

function plainText(output: CodeOutput): string | null {
  const text = output.content?.data?.['text/plain']
  return typeof text === 'string' ? text : null
}

function streamName(output: CodeOutput): 'stdout' | 'stderr' {
  return output.content?.name === 'stderr' ? 'stderr' : 'stdout'
}

function OutputItem({ output }: { output: CodeOutput }) {
  const image = isImage(output)
  if (image) {
    return (
      <figure className="my-2">
        {/* 沙箱内 matplotlib 生成的 PNG（base64） */}
        <img
          src={`data:image/png;base64,${image}`}
          alt="程序输出的图表"
          className="max-w-full rounded-[8px] border border-border bg-white"
        />
        <figcaption className="mt-1 text-xs text-muted">程序输出的图表</figcaption>
      </figure>
    )
  }

  if (output.msg_type === 'error') {
    return (
      <pre
        data-testid="codelab-output-error"
        className="whitespace-pre-wrap break-words rounded-[8px] border border-danger/40 bg-danger/5 p-2 text-xs leading-relaxed text-danger"
      >
        {output.content?.text ?? ''}
      </pre>
    )
  }

  if (output.msg_type === 'stream') {
    const name = streamName(output)
    return (
      <pre
        data-testid={`codelab-output-${name}`}
        className={[
          'whitespace-pre-wrap break-words rounded-[8px] border p-2 text-xs leading-relaxed',
          name === 'stderr'
            ? 'border-warn/40 bg-warn/5 text-warn'
            : 'border-border bg-surface-sunken text-fg',
        ].join(' ')}
      >
        {output.content?.text ?? ''}
      </pre>
    )
  }

  // display_data / execute_result 且没有图片
  const text = plainText(output)
  if (text !== null) {
    return (
      <pre
        data-testid="codelab-output-result"
        className="whitespace-pre-wrap break-words rounded-[8px] border border-border bg-surface p-2 text-xs leading-relaxed text-fg"
      >
        {text}
      </pre>
    )
  }

  // 兜底：仅在没有已知结构时才回退到 JSON 展示
  return (
    <pre
      data-testid="codelab-output-raw"
      className="whitespace-pre-wrap break-words rounded-[8px] border border-border bg-surface p-2 text-xs text-muted"
    >
      {JSON.stringify(output.content ?? {}, null, 2)}
    </pre>
  )
}

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  SUCCESS: { text: '运行成功', className: 'text-accent' },
  FAILED: { text: '运行出错', className: 'text-danger' },
  TIMEOUT: { text: '运行超时', className: 'text-warn' },
  ERROR: { text: '沙箱错误', className: 'text-danger' },
}

export function CodeOutputPanel({ run }: { run: CodeRun | null }) {
  if (!run) {
    return (
      <p className="text-sm text-muted">点击「运行」查看程序输出。</p>
    )
  }

  const status = STATUS_LABEL[run.status] ?? { text: run.status, className: 'text-muted' }

  return (
    <div className="space-y-2" data-testid="codelab-output-panel">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className={`font-semibold ${status.className}`}>{status.text}</span>
        {run.execution_time_ms !== null ? (
          <span className="text-muted">耗时 {run.execution_time_ms} ms</span>
        ) : null}
        {run.exit_code !== null ? <span className="text-muted">退出码 {run.exit_code}</span> : null}
      </div>

      {run.outputs.length === 0 ? (
        <p className="text-sm text-muted">
          {run.error ?? '程序没有产生任何输出。可以在代码里使用 print() 查看结果。'}
        </p>
      ) : (
        run.outputs.map((output, index) => <OutputItem key={index} output={output} />)
      )}

      {/* 有输出但也有 error（例如超时且有部分输出）时，额外说明一句 */}
      {run.error && run.outputs.length > 0 ? (
        <p className="text-xs text-danger">{run.error}</p>
      ) : null}
    </div>
  )
}
