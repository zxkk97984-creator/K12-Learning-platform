import { create } from 'zustand'

import type { Message } from '@/entities/conversation/types'
import { useCompanionStore } from '@/features/companion'
import { conversationService } from '@/mocks/services'
import { quizService } from '@/mocks/services'
import type { SendMessageCallbacks, StreamErrorEvent } from '@/shared/api/conversation-service'
import type { ScreenContext } from '@/features/screen-context/types'

import { INTENT_AI_STATE } from '../data/intents'
import type { ChatMessage, ConversationIntent } from '../types'

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
let loadPromise: Promise<void> | null = null
let activeAbortController: AbortController | undefined

const INTENT_PROMPTS: Record<ConversationIntent, string> = {
  explain: '解释当前内容',
  summary: '总结本页',
  quiz: '给我出题',
  'check-in': '你在吗？',
  selected: '解释我选中的内容',
  memory: '我有什么学习记忆？',
  'memory-dispute': '我不认可这条记忆',
  'profile-question': '为什么这样判断我？',
  'profile-why-transfer': '为什么说我的应用迁移仍需观察？',
  'profile-why-pace': '为什么这样判断我的学习节奏？',
  'profile-why-question': '为什么这样判断我的提问习惯？',
  'profile-why-change': '最近我有什么变化？',
  'presence-ask': '霜铃在吗？',
  'today-learn': '今天学什么？',
  'continue-yesterday': '继续昨天的内容',
  'recent-status': '看看最近学习状态',
  'recommend-next': '推荐下一本',
  'book-fit': '这本书适合我吗？',
  'book-why-1': '为什么推荐这本书？',
  'book-why-2': '这本书为什么适合我？',
  'book-why-3': '下一步为什么学这个？',
  'give-example': '举个例子',
  'give-hint': '给我一点提示',
  'another-way': '换一种讲法',
  'why-wrong': '为什么出错？',
  'quiz-requestion': '再出一道类似的题',
  'quiz-detail': '解释这份测验记录',
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

function errorText(error: StreamErrorEvent | Error): string {
  if ('code' in error && error.code) return `${error.message}（${error.code}）`
  return error.message || '网络似乎开了小差，霜铃没有收到完整的内容。'
}

function intentPrompt(intent: ConversationIntent, selectedText?: string): string {
  if (intent === 'selected' && selectedText) return `解释我选中的“${selectedText}”`
  return INTENT_PROMPTS[intent]
}

interface ConversationStore {
  messages: ChatMessage[]
  conversationId: string | null
  loaded: boolean
  load: () => Promise<void>
  send: (raw: string, screenContext?: ScreenContext) => Promise<void>
  abortCurrent: () => void
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
  conversationId: null,
  loaded: false,

  async load() {
    if (get().loaded) return
    if (loadPromise) return loadPromise
    loadPromise = (async () => {
      try {
        const conversations = await conversationService.getConversations({
          status: 'ACTIVE',
          limit: 1,
        })
        const conversation = conversations[0]
        if (!conversation) {
          set({ loaded: true })
          return
        }
        const serviceMessages = await conversationService.getMessages(
          conversation.conversation_id,
          { sort: 'asc' },
        )
        set({
          conversationId: conversation.conversation_id,
          messages: serviceMessages.map(toChatMessage),
          loaded: true,
        })
      } catch {
        set({
          loaded: true,
          messages: [
            {
              id: nextId(),
              role: 'ai',
              kind: 'error',
              content: '对话历史暂时加载失败，请稍后重试。',
              meta: '历史加载失败',
            },
          ],
        })
      } finally {
        loadPromise = null
      }
    })()
    return loadPromise
  },

  async send(raw: string, screenContext?: ScreenContext) {
    const text = raw.trim()
    if (!text) return
    await get().load()
    let conversationId = get().conversationId
    if (!conversationId) {
      const conversation = await conversationService.createConversation({ channel: 'TEXT' })
      conversationId = conversation.conversation_id
      set({ conversationId })
    }

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

    const abortController = new AbortController()
    activeAbortController?.abort()
    activeAbortController = abortController
    let assistantId: string | null = null
    let assistantContent = ''
    let errorShown = false

    const removeTyping = () => {
      set((state) => ({ messages: state.messages.filter((message) => message.id !== typingId) }))
    }
    const showError = (error: StreamErrorEvent | Error) => {
      if (errorShown) return
      errorShown = true
      set((state) => ({
        messages: [
          ...state.messages.filter((message) => message.id !== typingId),
          {
            id: nextId(),
            role: 'ai',
            kind: 'error',
            content: errorText(error),
            meta: '网络错误',
          },
        ],
      }))
      useCompanionStore.getState().setAiState('idle')
    }
    const upsertAssistant = (id: string, patch: Partial<ChatMessage>) => {
      set((state) => {
        const exists = state.messages.some((message) => message.id === id)
        if (!exists) {
          return {
            messages: [
              ...state.messages.filter((message) => message.id !== typingId),
              {
                id,
                role: 'ai',
                kind: 'text',
                content: '',
                meta: '霜铃 · 连续会话',
                streaming: true,
                ...patch,
              },
            ],
          }
        }
        return {
          messages: state.messages.map((message) =>
            message.id === id ? { ...message, ...patch } : message,
          ),
        }
      })
    }

    try {
      const input = screenContext
        ? { content: text, screen_context: screenContext }
        : { content: text }
      const callbacks: SendMessageCallbacks = {
        signal: abortController.signal,
        onStart: (event) => {
          assistantId = event.message_id
          assistantContent = ''
          upsertAssistant(event.message_id, { content: '', streaming: true })
        },
        onDelta: (event) => {
          assistantId ??= event.message_id
          assistantContent += event.delta
          upsertAssistant(assistantId, { content: assistantContent, streaming: true })
        },
        onTextDone: (event) => {
          assistantId ??= event.message_id
          assistantContent = event.content
          upsertAssistant(assistantId, { content: assistantContent, streaming: true })
        },
        onToolStart: (event) => {
          set((state) => ({
            messages: [
              ...state.messages,
              {
                id: `tool-${event.tool_run_id}`,
                role: 'ai',
                kind: 'tool',
                content: `${event.tool} · 正在处理中…`,
                meta: '',
              },
            ],
          }))
        },
        onToolResult: (event) => {
          set((state) => ({
            messages: state.messages.map((message) =>
              message.id === `tool-${event.tool_run_id}`
                ? {
                    ...message,
                    content:
                      event.status === 'success'
                        ? `${event.tool} · 已完成`
                        : `${event.tool} · 处理失败`,
                  }
                : message,
            ),
          }))
        },
        onDone: (event) => {
          assistantId ??= event.message_id
          upsertAssistant(assistantId, { content: assistantContent, streaming: false })
          removeTyping()
          useCompanionStore.getState().setAiState('speaking')
        },
        onError: (error) => {
          if (error instanceof Error && isAbortError(error)) return
          showError(error)
        },
      }
      await conversationService.sendMessage(conversationId, input, callbacks)
    } catch (error) {
      if (!isAbortError(error)) showError(error instanceof Error ? error : new Error(String(error)))
      else removeTyping()
    } finally {
      if (activeAbortController === abortController) activeAbortController = undefined
    }
  },

  runIntent(intent: ConversationIntent, selectedText?: string) {
    useCompanionStore.getState().setAiState(INTENT_AI_STATE[intent] ?? 'speaking')
    const text = intentPrompt(intent, selectedText)
    if (intent === 'quiz') {
      void get()
        .send(text)
        .then(() => get().runQuizToolFlow())
        .catch(() => undefined)
      return
    }
    void get().send(text)
  },

  async retry() {
    const lastUserMessage = [...get().messages].reverse().find((message) => message.role === 'user')
    set((state) => ({ messages: state.messages.filter((message) => message.kind !== 'error') }))
    if (lastUserMessage) await get().send(lastUserMessage.content)
  },

  abortCurrent: () => {
    activeAbortController?.abort()
    activeAbortController = undefined
    if (streamTimer !== undefined) window.clearInterval(streamTimer)
    streamTimer = undefined
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
        conversation_id: get().conversationId ?? 'conv-1',
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
