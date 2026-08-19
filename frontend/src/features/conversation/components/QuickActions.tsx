import { useLocation } from 'react-router-dom'

import { QUICK_ACTIONS } from '@/mocks/data/conversation'

import { useConversationStore } from '../store/conversation-store'

function quickActionKey(pathname: string): string {
  if (pathname === '/home') return 'home'
  if (pathname === '/library' || pathname.startsWith('/books/')) return 'library'
  if (pathname.startsWith('/learn/')) return 'reader'
  if (pathname.startsWith('/quizzes/') && pathname !== '/quizzes') return 'quiz-detail'
  if (pathname === '/quizzes') return 'quizzes'
  if (pathname.startsWith('/profile')) return 'profile'
  return 'home'
}

export function QuickActions() {
  const location = useLocation()
  const runIntent = useConversationStore((state) => state.runIntent)
  const actions = QUICK_ACTIONS[quickActionKey(location.pathname)] ?? QUICK_ACTIONS.home

  return (
    <div className="flex gap-1.5 overflow-x-auto px-4 pb-2.5">
      {actions.map(([intent, label]) => (
        <button
          key={intent}
          type="button"
          className="shrink-0 rounded-full border border-border bg-surface px-2.5 py-1.5 text-[10px] text-muted hover:border-fg hover:text-fg"
          onClick={() => runIntent(intent as Parameters<typeof runIntent>[0])}
        >
          {label}
        </button>
      ))}
      <button
        type="button"
        className="shrink-0 rounded-full border border-border bg-surface px-2.5 py-1.5 text-[10px] text-muted"
        title="语音聊天（Phase 9 实现）"
      >
        语音聊天
      </button>
    </div>
  )
}
