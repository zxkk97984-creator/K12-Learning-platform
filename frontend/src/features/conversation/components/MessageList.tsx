import { useEffect, useRef } from 'react'

import { useCompanionStore } from '@/features/companion'
import { QuizCard } from '@/features/quiz'

import { useConversationStore } from '../store/conversation-store'
import type { ChatMessage } from '../types'
import { MarkdownMessage } from './MarkdownMessage'

function MessageRow({
  message,
  onRetry,
  onClosePanel,
}: {
  message: ChatMessage
  onRetry: () => void
  onClosePanel: () => void
}) {
  if (message.kind === 'tool') {
    return (
      <div className="flex justify-center">
        <span className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1.5 font-mono text-[9px] text-muted">
          <i className="h-1.5 w-1.5 rounded-full bg-accent" />
          {message.content}
        </span>
      </div>
    )
  }

  if (message.kind === 'typing') {
    return (
      <div className="flex justify-start">
        <span className="inline-flex min-w-12 items-center gap-1 rounded-[13px_13px_13px_4px] border border-border bg-surface px-3 py-2.5">
          <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" />
          <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: '0.12s' }} />
          <i className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: '0.24s' }} />
        </span>
      </div>
    )
  }

  if (message.kind === 'error') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[89%] rounded-[13px_13px_13px_4px] border border-muted bg-fg-soft p-3">
          <p className="text-[13px] leading-relaxed text-fg">
            {message.content}
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="rounded-[7px] border border-border bg-surface px-2.5 py-1 text-[11px] text-fg hover:border-fg"
              onClick={onRetry}
            >
              重试
            </button>
            <button
              type="button"
              className="rounded-[7px] border border-border bg-surface px-2.5 py-1 text-[11px] text-fg hover:border-fg"
              onClick={onClosePanel}
            >
              稍后再问
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (message.kind === 'refuse') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[89%] rounded-[13px_13px_13px_4px] border border-border bg-surface p-3">
          <p className="text-[13px] leading-relaxed text-fg">
            <MarkdownMessage content={message.content} />
          </p>
          <p className="mt-1.5 text-[12px] text-muted">
            你可以试试：「解释训练数据」「给我出题」
          </p>
        </div>
      </div>
    )
  }

  if (message.kind === 'quiz') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[89%]">
          <div className="rounded-[13px_13px_13px_4px] border border-border bg-surface p-3">
            <p className="text-[13px] leading-relaxed text-fg">
              <MarkdownMessage content={message.content} />
            </p>
            <QuizCard sessionId={message.quiz?.sessionId ?? ''} />
          </div>
          {message.meta ? (
            <span className="mt-1 block font-mono text-[9px] tracking-wider text-muted">
              {message.meta}
            </span>
          ) : null}
        </div>
      </div>
    )
  }

  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[89%]">
        <div
          className={
            isUser
              ? 'rounded-[13px_13px_4px_13px] border border-fg bg-fg p-2.5 text-[13px] leading-relaxed text-surface'
              : 'rounded-[13px_13px_13px_4px] border border-border bg-surface p-2.5 text-[13px] leading-relaxed text-fg'
          }
        >
          {isUser ? message.content : <MarkdownMessage content={message.content} />}
          {message.streaming ? (
            <span className="ml-0.5 inline-block h-[1em] w-px animate-pulse bg-fg align-[-0.15em]" />
          ) : null}
        </div>
        {message.meta ? (
          <span className={`mt-1 block font-mono text-[9px] tracking-wider text-muted ${isUser ? 'text-right' : ''}`}>
            {message.meta}
          </span>
        ) : null}
      </div>
    </div>
  )
}

export function MessageList() {
  const messages = useConversationStore((state) => state.messages)
  const retry = useConversationStore((state) => state.retry)
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const feed = feedRef.current
    if (feed) feed.scrollTop = feed.scrollHeight
  }, [messages])

  return (
    <div ref={feedRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
      {messages.map((message) => (
        <MessageRow
          key={message.id}
          message={message}
          onRetry={() => void retry()}
          onClosePanel={() => {
            useCompanionStore.getState().setOpen(false)
            useCompanionStore.getState().setAiState('idle')
          }}
        />
      ))}
    </div>
  )
}
