import type { ReactNode } from 'react'

/** T07 请求状态语义视图：Loading / Empty / Error 三种可组合状态。 */

type ResourceStateType = 'loading' | 'empty' | 'error'

interface ResourceStateProps {
  type: ResourceStateType
  /** 标题（默认按类型取文案） */
  title?: string
  /** 说明文字 */
  description?: string
  /** 错误时的可选 request ID（便于排查） */
  requestId?: string
  /** 重试回调；提供时渲染重试按钮 */
  onRetry?: () => void
  /** 空态时的可选动作 */
  action?: ReactNode
  /** 判断是否为空：仅供 success 且数据确实为空时调用 empty。 */
  isEmpty?: boolean
}

const DEFAULTS: Record<ResourceStateType, { title: string; description: string }> = {
  loading: { title: '正在加载', description: '' },
  empty: { title: '暂无内容', description: '这里还没有数据，稍后再来看看吧。' },
  error: { title: '暂时无法加载', description: '请稍后重试；问题仍存在时可截图反馈。' },
}

export function ResourceState(props: ResourceStateProps) {
  const fallback = DEFAULTS[props.type]
  const title = props.title ?? fallback.title
  const description = props.description ?? fallback.description

  return (
    <div
      role={props.type === 'error' ? 'alert' : 'status'}
      data-testid={`resource-${props.type}`}
      className="flex flex-col items-center gap-3 rounded-[14px] border border-border bg-surface px-6 py-10 text-center"
    >
      <div className="flex items-center gap-2">
        {props.type === 'error' ? (
          <span aria-hidden className="text-accent">⚠</span>
        ) : null}
        <h3 className="font-display text-lg text-fg">{title}</h3>
      </div>
      {description ? <p className="max-w-[46ch] text-sm leading-relaxed text-muted">{description}</p> : null}
      {props.type === 'error' && props.requestId ? (
        <p className="font-mono text-xs text-muted">请求编号：{props.requestId}</p>
      ) : null}
      {props.onRetry ? (
        <button
          type="button"
          onClick={props.onRetry}
          className="mt-1 min-h-[44px] rounded-[12px] border border-border bg-surface px-4 py-2 text-sm text-fg hover:border-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          重试
        </button>
      ) : null}
      {props.action ? <div className="mt-1">{props.action}</div> : null}
    </div>
  )
}
