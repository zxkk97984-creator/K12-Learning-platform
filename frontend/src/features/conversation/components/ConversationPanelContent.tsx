import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { useCompanionStore } from '@/features/companion'
import { useScreenContext } from '@/features/screen-context'

import { ChatComposer } from './ChatComposer'
import { MessageList } from './MessageList'
import { QuickActions } from './QuickActions'
import { useConversationStore } from '../store/conversation-store'

function contextLabel(pathname: string): string {
  if (pathname.startsWith('/learn/')) return 'AI 不是魔法 / 第3章 / 训练数据'
  if (pathname === '/quizzes' || pathname.startsWith('/quizzes/')) return '测验记录'
  if (pathname.startsWith('/profile')) return '学习画像 · 依据真实学习记录'
  if (pathname === '/library' || pathname.startsWith('/books/')) return '书库'
  if (pathname === '/settings') return '设置'
  return '首页 · 最近学习记录'
}

export function ConversationPanelContent() {
  const open = useCompanionStore((state) => state.open)
  const load = useConversationStore((state) => state.load)
  const abortCurrent = useConversationStore((state) => state.abortCurrent)
  const location = useLocation()
  const { screenContext } = useScreenContext()

  useEffect(() => {
    if (open) void load()
    return () => abortCurrent()
  }, [open, load, abortCurrent])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-fg-soft px-4 py-2 text-[10px] text-muted">
        <i className="h-1.5 w-1.5 rounded-full bg-accent" />
        <span>
          正在参考：
          <strong className="text-fg">
            {screenContext.pageType === 'chapter_reader' && screenContext.chapterTitle
              ? `${screenContext.chapterTitle}${
                  screenContext.visibleSection ? ` / ${screenContext.visibleSection}` : ''
                }`
              : contextLabel(location.pathname)}
          </strong>
        </span>
      </div>
      <MessageList />
      <QuickActions />
      <ChatComposer />
    </div>
  )
}
