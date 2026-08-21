import { create } from 'zustand'

import type { Message } from '@/entities/conversation/types'
import { useCompanionStore } from '@/features/companion'
import { conversationService } from '@/mocks/services'
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
  // 5-B：出题工具结束后，教师消息以 TEXT 落库并携带 quiz_session_id 元数据。
  // 历史加载时还原为对话内 QuizCard，避免刷新后卡片消失。
  if (
    message.type === 'TEXT' &&
    message.metadata?.tool === 'quiz' &&
    typeof message.metadata.quiz_session_id === 'string'
  ) {
    return {
      id: message.message_id,
      role: 'ai',
      kind: 'quiz',
      content: message.content,
      meta: 'Quiz Skill 已创建 · 正式测验已记录',
      quiz: { sessionId: message.metadata.quiz_session_id },
    }
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

function toChatMessages(messages: Message[]): ChatMessage[] {
  return messages
    .filter(
      (message) =>
        !(message.role === 'TEACHER' && message.type === 'TEXT' && !message.content.trim()),
    )
    .map(toChatMessage)
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
  ensureConversationId: () => Promise<string>
  refresh: () => Promise<void>
  send: (raw: string, screenContext?: ScreenContext) => Promise<void>
  abortCurrent: () => void
  runIntent: (intent: ConversationIntent, selectedText?: string) => void
  retry: () => void
  /** 追加一条 AI 文本消息（quiz 结果/提示等，非流式） */
  appendAiText: (content: string, meta: string) => void
  /** 内部：逐字流式输出（22ms/字），组件不直接调用 */
  pushStreaming: (text: string, meta: string) => void
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
          messages: toChatMessages(serviceMessages),
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

  async ensureConversationId() {
    await get().load()
    let conversationId = get().conversationId
    if (!conversationId) {
      const conversation = await conversationService.createConversation({ channel: 'TEXT' })
      conversationId = conversation.conversation_id
      set({ conversationId })
    }
    return conversationId
  },

  async refresh() {
    const conversationId = get().conversationId
    if (!conversationId) return
    try {
      const serviceMessages = await conversationService.getMessages(conversationId, {
        sort: 'asc',
      })
      set({ messages: toChatMessages(serviceMessages), loaded: true })
    } catch {
      // 语音 final 后的历史刷新失败不阻塞状态机。
    }
  },

  async send(raw: string, screenContext?: ScreenContext) {
    const text = raw.trim()
    if (!text) return
    await get().load()
    const conversationId = await get().ensureConversationId()

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

    const removePendingMessages = () => {
      set((state) => ({
        messages: state.messages.filter(
          (message) =>
            message.id !== typingId &&
            !(assistantId && message.id === assistantId && !message.content.trim()),
        ),
      }))
    }
    const showError = (error: StreamErrorEvent | Error) => {
      if (errorShown) return
      errorShown = true
      set((state) => ({
        messages: [
          ...state.messages.filter(
            (message) =>
              message.id !== typingId &&
              !(assistantId && message.id === assistantId && !message.content.trim()),
          ),
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
    const toolMessageId = (toolRunId: string) => `tool-${toolRunId}`
    const isRecord = (value: unknown): value is Record<string, unknown> =>
      typeof value === 'object' && value !== null

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
          if (event.tool === 'quiz') {
            set((state) => ({
              messages: [
                ...state.messages,
                {
                  id: toolMessageId(event.tool_run_id),
                  role: 'ai',
                  kind: 'tool',
                  content: '正在生成题目…',
                  meta: '',
                },
              ],
            }))
            return
          }
          set((state) => ({
            messages: [
              ...state.messages,
              {
                id: toolMessageId(event.tool_run_id),
                role: 'ai',
                kind: 'tool',
                content: `${event.tool} · 正在处理中…`,
                meta: '',
              },
            ],
          }))
        },
        onToolResult: (event) => {
          if (event.tool === 'quiz') {
            const payload = isRecord(event.payload) ? event.payload : {}
            const sessionId =
              typeof payload.quiz_session_id === 'string' ? payload.quiz_session_id : null
            set((state) => ({
              messages: state.messages.map((message) =>
                message.id === toolMessageId(event.tool_run_id)
                  ? {
                      ...message,
                      kind: event.status === 'success' ? 'quiz' : 'tool',
                      content:
                        event.status === 'success'
                          ? 'Quiz Skill 已创建 · 正式测验已记录'
                          : 'Quiz Skill 生成失败，请稍后再试',
                      quiz: sessionId ? { sessionId } : null,
                    }
                  : message,
              ),
            }))
            return
          }
          set((state) => ({
            messages: state.messages.map((message) =>
              message.id === toolMessageId(event.tool_run_id)
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
          if (assistantContent.trim()) {
            upsertAssistant(assistantId, { content: assistantContent, streaming: false })
          }
          removePendingMessages()
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
      else removePendingMessages()
    } finally {
      if (activeAbortController === abortController) activeAbortController = undefined
    }
  },

  runIntent(intent: ConversationIntent, selectedText?: string) {
    useCompanionStore.getState().setAiState(INTENT_AI_STATE[intent] ?? 'speaking')
    const text = intentPrompt(intent, selectedText)
    if (intent === 'quiz') {
      // 5-D：真实链路——「给我出题」只发文本，后端 SSE 返回 tool.start/tool.result，
      // store 用 tool.result 的 quiz_session_id 渲染真实 QuizCard（不再走 Mock 创建）。
      void get().send(text).catch(() => undefined)
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

  // 以下内部方法挂到 store（保持单一数据源；组件不直接调用）
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
}))
