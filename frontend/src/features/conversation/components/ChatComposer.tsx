import { useState, type KeyboardEvent } from 'react'

import { useScreenContext } from '@/features/screen-context'

import { useConversationStore } from '../store/conversation-store'

export function ChatComposer() {
  const [value, setValue] = useState('')
  const send = useConversationStore((state) => state.send)
  const { screenContext } = useScreenContext()

  const submit = () => {
    if (!value.trim()) return
    void send(value, screenContext)
    setValue('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      className="flex items-end gap-2 border-t border-border px-3 pt-2.5 pb-3"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="问问霜铃，比如：那它为什么会出错？"
        aria-label="消息输入"
        className="min-h-[42px] max-h-[88px] flex-1 resize-none rounded-[10px] border border-border bg-bg px-3 py-2.5 text-[13px] text-fg outline-none focus:border-fg"
      />
      <button
        type="submit"
        aria-label="发送消息"
        className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[10px] border border-fg bg-fg text-surface hover:bg-fg/85"
      >
        ↑
      </button>
    </form>
  )
}
