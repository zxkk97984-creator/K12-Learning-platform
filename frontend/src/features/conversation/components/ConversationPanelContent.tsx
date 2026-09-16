import { useEffect } from 'react'

import { useCompanionStore } from '@/features/companion'
import { useToastStore } from '@/features/feedback'
import { useScreenContext } from '@/features/screen-context'

import { ChatComposer } from './ChatComposer'
import { MessageList } from './MessageList'
import { QuickActions } from './QuickActions'
import { useConversationStore } from '../store/conversation-store'

// Phase 2-A5：仅基于真实 ScreenContext 展示；无页面细节时给通用标签，
// 不再使用「AI 不是魔法 / 第3章」等硬编码兜底文案。
function contextLabel(pageType: string): string {
  switch (pageType) {
    case 'chapter_reader':
      return '章节阅读中'
    case 'book_detail':
      return '书籍详情'
    case 'library':
      return '书库'
    case 'quiz_history':
      return '测验记录'
    case 'profile':
      return '学习画像 · 依据真实学习记录'
    case 'settings':
      return '设置'
    default:
      return '首页 · 最近学习记录'
  }
}

export function ConversationPanelContent() {
  const open = useCompanionStore((state) => state.open)
  const load = useConversationStore((state) => state.load)
  const abortCurrent = useConversationStore((state) => state.abortCurrent)
  const history = useConversationStore((state) => state.history)
  const conversationId = useConversationStore((state) => state.conversationId)
  const loadHistory = useConversationStore((state) => state.loadHistory)
  const switchConversation = useConversationStore((state) => state.switchConversation)
  const startNewConversation = useConversationStore((state) => state.startNewConversation)
  const setConversationStatus = useConversationStore(
    (state) => state.setConversationStatus,
  )
  const showToast = useToastStore((state) => state.showToast)
  const { screenContext } = useScreenContext()

  useEffect(() => {
    if (open) {
      void load()
      void loadHistory()
    }
    return () => abortCurrent()
  }, [open, load, abortCurrent, loadHistory])

  // Phase 4：删除需要确认；归档直接执行（可从历史切回）
  const handleDelete = async () => {
    if (!conversationId) return
    if (!window.confirm('确认删除这段对话？删除后不可再继续对话。')) return
    await setConversationStatus(conversationId, 'DELETED')
    showToast('对话已删除')
  }

  const handleArchive = async () => {
    if (!conversationId) return
    await setConversationStatus(conversationId, 'ARCHIVED')
    showToast('对话已归档，可在历史中查看')
  }

  const referenceLabel =
    screenContext.pageType === 'chapter_reader' && screenContext.chapterTitle
      ? `${screenContext.chapterTitle}${
          screenContext.visibleSection ? ` / ${screenContext.visibleSection}` : ''
        }`
      : contextLabel(screenContext.pageType)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-fg-soft px-4 py-2 text-[10px] text-muted">
        <i className="h-1.5 w-1.5 rounded-full bg-accent" />
        <span>
          正在参考：
          <strong className="text-fg">{referenceLabel}</strong>
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          <select
            aria-label="对话历史"
            data-testid="conversation-history"
            value={conversationId ?? ''}
            onChange={(event) => {
              if (event.target.value && event.target.value !== conversationId) {
                void switchConversation(event.target.value)
              }
            }}
            className="max-w-[110px] rounded border border-border bg-surface px-1 py-0.5 text-[10px] text-fg"
          >
            {!conversationId ? <option value="">选择会话</option> : null}
            {history.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {(entry.status === 'ARCHIVED' ? '[归档] ' : '') +
                  (entry.title || entry.last_message_preview || '未命名会话').slice(0, 14)}
              </option>
            ))}
          </select>
          <details className="relative">
            <summary
              aria-label="会话操作"
              className="cursor-pointer list-none rounded border border-border px-1.5 py-0.5 text-[10px] text-muted hover:border-fg hover:text-fg"
            >
              操作 ▾
            </summary>
            <div className="absolute right-0 z-10 mt-1 flex flex-col rounded-lg border border-border bg-surface shadow-soft">
              <button
                type="button"
                data-testid="conversation-new"
                aria-label="新对话"
                className="px-3 py-1.5 text-left text-[10px] text-fg hover:bg-fg-soft"
                onClick={() => void startNewConversation()}
              >
                新对话
              </button>
              {conversationId ? (
                <>
                  <button
                    type="button"
                    data-testid="conversation-archive"
                    aria-label="归档当前对话"
                    className="px-3 py-1.5 text-left text-[10px] text-fg hover:bg-fg-soft"
                    onClick={() => void handleArchive()}
                  >
                    归档
                  </button>
                  <button
                    type="button"
                    data-testid="conversation-delete"
                    aria-label="删除当前对话"
                    className="px-3 py-1.5 text-left text-[10px] text-fg hover:bg-red-400 hover:text-red-400"
                    onClick={() => void handleDelete()}
                  >
                    删除
                  </button>
                </>
              ) : null}
            </div>
          </details>
        </span>
      </div>
      <MessageList />
      <QuickActions />
      <ChatComposer />
    </div>
  )
}
