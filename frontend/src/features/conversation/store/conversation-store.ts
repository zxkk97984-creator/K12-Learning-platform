import { create } from 'zustand'

import type { Message } from '@/entities/conversation/types'
import { useCompanionStore } from '@/features/companion'
import { conversationService } from '@/mocks/services'
import { quizService } from '@/mocks/services'

import { INTENT_AI_STATE, currentIntentText } from '../data/intents'
import type { ChatMessage, ConversationIntent } from '../types'

const CONVERSATION_ID = 'conv-1'

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

let messageSeq = 100
function nextId(): string {
  messageSeq += 1
  return `chat-${messageSeq}`
}

function toChatMessage(message: Message): ChatMessage {
  if (message.type === 'TOOL_STATUS') {
    return { id: message.message_id, role: 'ai', kind: 'tool', content: message.content, meta: '' }
  }
  if (message.type === 'QUIZ') {
    return {
      id: message.message_id,
      role: 'ai',
      kind: 'quiz',
      content: message.content,
      meta: '第 1 题 / 共 3 题',
      quiz: { sessionId: String(message.metadata.quiz_session_id ?? '') },
    }
  }
  return {
    id: message.message_id,
    role: message.role === 'STUDENT' ? 'user' : 'ai',
    kind: 'text',
    content: message.content,
    meta: '',
  }
}

let streamTimer: number | undefined

interface ConversationStore {
  messages: ChatMessage[]
  loaded: boolean
  load: () => Promise<void>
  send: (raw: string) => Promise<void>
  runIntent: (intent: ConversationIntent, selectedText?: string) => void
  retry: () => void
  /** 追加一条 AI 文本消息（quiz 结果/提示等，非流式） */
  appendAiText: (content: string, meta: string) => void
  /** 内部：逐字流式输出（22ms/字），组件不直接调用 */
  pushStreaming: (text: string, meta: string) => void
  /** 内部：quiz intent 的 tool 状态流（900ms 后创建），quiz 卡由 1-H 渲染 */
  runQuizToolFlow: () => Promise<void>
}

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  messages: [],
  loaded: false,

  async load() {
    if (get().loaded) return
    const serviceMessages = await conversationService.getMessages(CONVERSATION_ID)
    set({ messages: serviceMessages.map(toChatMessage), loaded: true })
  },

  async send(raw: string) {
    const text = raw.trim()
    if (!text) return
    const userMessage: ChatMessage = {
      id: nextId(),
      role: 'user',
      kind: 'text',
      content: text,
      meta: '刚刚',
    }
    const typingId = nextId()
    set((state) => ({
      messages: [
        ...state.messages,
        userMessage,
        { id: typingId, role: 'ai', kind: 'typing', content: '' },
      ],
    }))
    useCompanionStore.getState().setAiState('thinking')

    await sleep(820)
    const state = get()
    const withoutTyping = state.messages.filter((message) => message.id !== typingId)

    if (text.includes('断网') || text.includes('网络')) {
      set({
        messages: [
          ...withoutTyping,
          {
            id: nextId(),
            role: 'ai',
            kind: 'error',
            content: '网络似乎开了小差，霜铃没有收到完整的内容。',
            meta: '网络错误',
          },
        ],
      })
      useCompanionStore.getState().setAiState('idle')
      return
    }
    if (text.includes('天气') || text.includes('股票') || text.includes('游戏')) {
      set({
        messages: [
          ...withoutTyping,
          {
            id: nextId(),
            role: 'ai',
            kind: 'refuse',
            content: '这个问题不在霜铃的教学范围里。我们可以聊聊正在学的内容，或者换一个和课程有关的问题。',
            meta: '无法回答',
          },
        ],
      })
      useCompanionStore.getState().setAiState('confused')
      return
    }

    // 普通/为什么分支：回复文案来自 MockConversationService（原型 sendMessage 文本）
    let reply = '我会把你的问题和当前这节内容连起来回答。'
    try {
      const assistant = await conversationService.sendMessage(CONVERSATION_ID, { content: text })
      reply = assistant.content
    } catch {
      reply = '我会把你的问题和当前这节内容连起来回答。'
    }
    set({ messages: withoutTyping })
    get().pushStreaming(reply, '霜铃 · 连续会话')
  },

  runIntent(intent: ConversationIntent, selectedText?: string) {
    const text = currentIntentText(intent, selectedText)
    useCompanionStore.getState().setAiState(INTENT_AI_STATE[intent] ?? 'speaking')
    // 去重：同 content 不重复流式输出（对齐原型）
    if (get().messages.some((message) => message.content === text)) return
    if (intent === 'quiz') {
      get().runQuizToolFlow()
      return
    }
    get().pushStreaming(text, '霜铃 · 当前页面上下文')
  },

  async retry() {
    const state = get()
    const withoutError = state.messages.filter((message) => message.kind !== 'error')
    const typingId = nextId()
    set({ messages: [...withoutError, { id: typingId, role: 'ai', kind: 'typing', content: '' }] })
    await sleep(700)
    set((current) => ({ messages: current.messages.filter((message) => message.id !== typingId) }))
    get().pushStreaming(
      '网络恢复了。我重新回答：先把训练数据理解成“机器看过的例子”，再看这些例子怎样影响它之后的判断。',
      '霜铃 · 重试',
    )
  },

  appendAiText: (content: string, meta: string) => {
    set((state) => ({
      messages: [
        ...state.messages,
        { id: nextId(), role: 'ai', kind: 'text', content, meta },
      ],
    }))
  },

  // 以下两个内部方法挂到 store（保持单一数据源；组件不直接调用）
  pushStreaming: (text: string, meta: string) => {
    if (get().messages.some((message) => message.content === text)) return
    if (streamTimer !== undefined) window.clearInterval(streamTimer)
    const id = nextId()
    set((state) => ({
      messages: [
        ...state.messages,
        { id, role: 'ai', kind: 'text', content: '', meta, streaming: true },
      ],
    }))
    let index = 0
    streamTimer = window.setInterval(() => {
      index += 1
      const content = text.slice(0, index)
      set((state) => ({
        messages: state.messages.map((message) => (message.id === id ? { ...message, content } : message)),
      }))
      if (index >= text.length) {
        if (streamTimer !== undefined) window.clearInterval(streamTimer)
        streamTimer = undefined
        set((state) => ({
          messages: state.messages.map((message) =>
            message.id === id ? { ...message, content: text, streaming: false } : message,
          ),
        }))
        useCompanionStore.getState().setAiState('speaking')
      }
    }, 22)
  },

  runQuizToolFlow: async () => {
    useCompanionStore.getState().setAiState('encouraging')
    const toolId = nextId()
    set((state) => ({
      messages: [
        ...state.messages,
        { id: toolId, role: 'ai', kind: 'tool', content: 'Quiz Skill · 正在生成测验…', meta: '' },
      ],
    }))
    // 1-H：真正创建 q-live 会话（对齐原型 unshift q-live；失败回退历史 q1）
    let sessionId = 'q1'
    try {
      const session = await quizService.createQuizSession({
        conversation_id: CONVERSATION_ID,
        quiz_kind: 'AI_QUIZ',
      })
      sessionId = session.quiz_session_id
    } catch {
      sessionId = 'q1'
    }
    window.setTimeout(() => {
      set((state) => ({
        messages: state.messages.map((message) =>
          message.id === toolId ? { ...message, content: 'Quiz Skill 已创建 · 正式测验已记录' } : message,
        ),
      }))
      set((state) => ({
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: 'ai',
            kind: 'quiz',
            content: '根据这一段内容，试一道小题。',
            meta: '第 1 题 / 共 3 题',
            quiz: { sessionId },
          },
        ],
      }))
    }, 900)
  },
}))
