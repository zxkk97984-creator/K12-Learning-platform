import { create } from 'zustand'

import type { Message } from '@/entities/conversation/types'
import { currentTeacherName, useCompanionStore } from '@/features/companion'
import { conversationService } from '@/shared/services'
import { getToken } from '@/shared/api/auth'
import type { SendMessageCallbacks, StreamErrorEvent } from '@/shared/api/conversation-service'
import type { ScreenContext } from '@/features/screen-context/types'

import { INTENT_AI_STATE } from '../data/intents'
import type { ChatMessage, ConversationIntent } from '../types'

let messageSeq = 100

export interface ConversationHistoryEntry {
  id: string
  title: string | null
  status: 'ACTIVE' | 'ARCHIVED' | 'DELETED'
  teacher_role_name: string | null
  last_message_preview: string | null
  updated_at: string
}

const ACTIVE_CONVERSATION_KEY_PREFIX = 'shuangling-active-conversation:'

// 旧版无用户隔离的全局键：切换账号时只清理，不迁移给新用户。
const LEGACY_ACTIVE_CONVERSATION_KEY = 'shuangling-active-conversation'

function activeConversationKey(userId: string | null): string {
  return userId ? `${ACTIVE_CONVERSATION_KEY_PREFIX}${userId}` : LEGACY_ACTIVE_CONVERSATION_KEY
}

function currentUserId(): string | null {
  // 从 JWT payload 读取 sub；无 token 或解析失败返回 null。
  try {
    const token = getToken()
    if (!token) return null
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.sub === 'string' ? payload.sub : null
  } catch {
    return null
  }
}

/** 环境安全的持久化（node 测试环境无 window/localStorage 时静默跳过）。 */
function persistActiveConversation(id: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(activeConversationKey(currentUserId()), id)
}

function readActiveConversation(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(activeConversationKey(currentUserId()))
}

function clearActiveConversation(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(activeConversationKey(currentUserId()))
  window.localStorage.removeItem(LEGACY_ACTIVE_CONVERSATION_KEY)
}

type ConversationHistoryEntrySource = {
  conversation_id: string
  title: string | null
  status: string
  teacher_role: Record<string, unknown> | null
  last_message_preview?: string | null
  updated_at: string
}
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
      meta: '测验已创建 · 正式测验已记录',
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

// ---- 会话世代（T06 账号切换隔离）----
// 每次 reset/账号切换递增；异步操作在 await 前后校验，世代变了则丢弃结果，
// 避免 A 用户在 B 登录后返回后台回填 A 的消息。loadPromise 也按世代失效。
let sessionEpoch = 0

function currentEpoch(): number {
  return sessionEpoch
}

function bumpEpoch(): number {
  sessionEpoch += 1
  return sessionEpoch
}

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
  'presence-ask': '在吗？',
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
  'explain-question': '讲解这道题',
  'quiz-requestion': '再出一道类似的题',
  'quiz-detail': '解释这份测验记录',
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

function errorText(error: StreamErrorEvent | Error): string {
  if ('code' in error && error.code) return `${error.message}（${error.code}）`
  return error.message || `网络似乎开了小差，${currentTeacherName()}没有收到完整的内容。`
}

function intentPrompt(intent: ConversationIntent, selectedText?: string): string {
  if (intent === 'selected' && selectedText) return `解释我选中的“${selectedText}”`
  if (intent === 'presence-ask') return `${currentTeacherName()}在吗？`
  return INTENT_PROMPTS[intent]
}

interface ConversationStore {
  messages: ChatMessage[]
  conversationId: string | null
  loaded: boolean
  /** 记录 loaded 所属的会话世代：账号切换后世代变化，避免旧 loaded 短路。 */
  loadedEpoch: number
  /** 最后一次随消息发送的真实 ScreenContext（重试时复用；Phase 2-A2）。 */
  lastScreenContext: ScreenContext | null
  /** 最后一次发送的幂等键：重试必须复用，防止重复消息（Phase 5-A）。 */
  lastIdempotencyKey: string | null
  /** Phase 4：对话历史（ACTIVE + ARCHIVED，来自后端） */
  history: ConversationHistoryEntry[]
  historyLoaded: boolean
  load: () => Promise<void>
  ensureConversationId: () => Promise<string>
  refresh: () => Promise<void>
  send: (raw: string, screenContext?: ScreenContext, idempotencyKeyOverride?: string) => Promise<void>
  abortCurrent: () => void
  runIntent: (
    intent: ConversationIntent,
    selectedText?: string,
    screenContext?: ScreenContext,
  ) => void
  retry: () => void
  /** Phase 4：拉取历史（ACTIVE + ARCHIVED），按更新时间倒序 */
  loadHistory: () => Promise<void>
  /** 切换到指定会话并加载其消息 */
  switchConversation: (conversationId: string) => Promise<void>
  /** 新建对话并切换；「清空当前对话」= 开启新会话，旧会话保留在历史中可切回 */
  startNewConversation: () => Promise<string>
  /** 归档 / 软删除指定会话；若作用于当前会话则自动切换到最新 ACTIVE 或新建 */
  setConversationStatus: (conversationId: string, status: 'ARCHIVED' | 'DELETED') => Promise<void>
  /** 追加一条 AI 文本消息（quiz 结果/提示等，非流式） */
  appendAiText: (content: string, meta: string) => void
  /** 内部：逐字流式输出（22ms/字），组件不直接调用 */
  pushStreaming: (text: string, meta: string) => void
  /** T06：账号切换/登出/401 时清空会话状态并递增世代，中止在途请求。 */
  reset: () => void
}

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  messages: [],
  conversationId: null,
  loaded: false,
  loadedEpoch: 0,
  lastScreenContext: null,
  history: [],
  historyLoaded: false,
  lastIdempotencyKey: null,

  async load() {
    const epoch = currentEpoch()
    if (get().loaded && epoch === get().loadedEpoch) return
    if (loadPromise) return loadPromise
    loadPromise = (async () => {
      try {
        let conversation = (
          await conversationService.getConversations({ status: 'ACTIVE', limit: 20 })
        )[0]
        // Phase 4：刷新后恢复上次会话（localStorage 记录优先）
        let storedId = readActiveConversation()
        if (storedId && !conversation) {
          try {
            const detail = await conversationService.getConversation(storedId)
            if (detail.status !== 'DELETED') {
              conversation = {
                ...detail,
                teacher_role: detail.teacher_role ?? null,
              } as typeof conversation
            }
          } catch {
            clearActiveConversation()
            storedId = null
          }
        }
        // 世代失效：等待期间账号已切换，丢弃结果。
        if (epoch !== currentEpoch()) return
        if (!conversation) {
          set({ loaded: true, loadedEpoch: epoch })
          return
        }
        persistActiveConversation(conversation.conversation_id)
        const serviceMessages = await conversationService.getMessages(
          conversation.conversation_id,
          { sort: 'asc' },
        )
        if (epoch !== currentEpoch()) return
        set({
          conversationId: conversation.conversation_id,
          messages: toChatMessages(serviceMessages),
          loaded: true,
          loadedEpoch: epoch,
        })
      } catch {
        if (epoch !== currentEpoch()) return
        set({
          loaded: true,
          loadedEpoch: epoch,
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
      persistActiveConversation(conversationId)
    }
    return conversationId
  },

  async refresh() {
    const conversationId = get().conversationId
    if (!conversationId) return
    const epoch = currentEpoch()
    try {
      const serviceMessages = await conversationService.getMessages(conversationId, {
        sort: 'asc',
      })
      if (epoch !== currentEpoch()) return
      set({ messages: toChatMessages(serviceMessages), loaded: true, loadedEpoch: epoch })
    } catch {
      // 语音 final 后的历史刷新失败不阻塞状态机。
    }
  },

  async send(raw: string, screenContext?: ScreenContext, idempotencyKeyOverride?: string) {
    const text = raw.trim()
    if (!text) return
    await get().load()
    const conversationId = await get().ensureConversationId()
    const sendEpoch = currentEpoch()
    // 记录最后一次真实上下文与幂等键，供「重试」复用（Phase 2-A2 / 5-A）
    if (screenContext) set({ lastScreenContext: screenContext })
    const idempotencyKey = idempotencyKeyOverride ?? crypto.randomUUID()
    set({ lastIdempotencyKey: idempotencyKey })

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

    const stale = () => sendEpoch !== currentEpoch()
    const removePendingMessages = () => {
      if (stale()) return
      set((state) => ({
        messages: state.messages.filter(
          (message) =>
            message.id !== typingId &&
            !(assistantId && message.id === assistantId && !message.content.trim()),
        ),
      }))
    }
    const showError = (error: StreamErrorEvent | Error) => {
      if (stale() || errorShown) return
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
      if (stale()) return
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
                meta: `${currentTeacherName()} · 连续会话`,
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
          if (stale()) return
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
          if (stale()) return
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
                          ? '测验已创建 · 正式测验已记录'
                          : '测验生成失败，请稍后再试',
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
          if (stale()) return
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
      await conversationService.sendMessage(conversationId, input, callbacks, idempotencyKey)
    } catch (error) {
      if (!isAbortError(error)) showError(error instanceof Error ? error : new Error(String(error)))
      else removePendingMessages()
    } finally {
      if (activeAbortController === abortController) activeAbortController = undefined
    }
  },

  runIntent(intent: ConversationIntent, selectedText?: string, screenContext?: ScreenContext) {
    useCompanionStore.getState().setAiState(INTENT_AI_STATE[intent] ?? 'speaking')
    const text = intentPrompt(intent, selectedText)
    if (intent === 'quiz') {
      // 5-D：真实链路——「给我出题」只发文本，后端 SSE 返回 tool.start/tool.result，
      // store 用 tool.result 的 quiz_session_id 渲染真实 QuizCard（不再走 Mock 创建）。
      void get().send(text, screenContext).catch(() => undefined)
      return
    }
    void get().send(text, screenContext)
  },

  async retry() {
    const lastUserMessage = [...get().messages].reverse().find((message) => message.role === 'user')
    set((state) => ({ messages: state.messages.filter((message) => message.kind !== 'error') }))
    if (lastUserMessage) {
      // Phase 5-A 整改：重试必须复用最后一次发送的幂等键，
      // 避免网络中断重试产生第二条学生消息。
      await get().send(
        lastUserMessage.content,
        get().lastScreenContext ?? undefined,
        get().lastIdempotencyKey ?? undefined,
      )
    }
  },

  async loadHistory() {
    try {
      const [active, archived] = await Promise.all([
        conversationService.getConversations({ status: 'ACTIVE', limit: 50 }),
        conversationService.getConversations({ status: 'ARCHIVED', limit: 50 }),
      ])
      const toEntry = (item: ConversationHistoryEntrySource): ConversationHistoryEntry => ({
        id: item.conversation_id,
        title: item.title,
        status: item.status as ConversationHistoryEntry['status'],
        teacher_role_name:
          item.teacher_role && typeof item.teacher_role.name === 'string'
            ? (item.teacher_role.name as string)
            : null,
        last_message_preview:
          (item as unknown as { last_message_preview?: string | null })
            .last_message_preview ?? null,
        updated_at: item.updated_at,
      })
      const merged = [...active.map(toEntry), ...archived.map(toEntry)].sort(
        (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
      )
      set({ history: merged, historyLoaded: true })
    } catch {
      set({ historyLoaded: true })
    }
  },

  async switchConversation(targetId: string) {
    if (get().conversationId === targetId) return
    activeAbortController?.abort()
    activeAbortController = undefined
    persistActiveConversation(targetId)
    const serviceMessages = await conversationService.getMessages(targetId, { sort: 'asc' })
    set({ conversationId: targetId, messages: toChatMessages(serviceMessages), loaded: true })
    void get().loadHistory()
  },

  async startNewConversation() {
    const created = await conversationService.createConversation({ channel: 'TEXT', title: null })
    persistActiveConversation(created.conversation_id)
    set({ conversationId: created.conversation_id, messages: [], loaded: true })
    void get().loadHistory()
    return created.conversation_id
  },

  async setConversationStatus(targetId: string, status: 'ARCHIVED' | 'DELETED') {
    await conversationService.updateConversation(targetId, { status })
    if (get().conversationId === targetId) {
      await get().loadHistory()
      const nextActive = get().history.find((entry) => entry.status === 'ACTIVE')
      if (nextActive) await get().switchConversation(nextActive.id)
      else await get().startNewConversation()
    } else {
      await get().loadHistory()
    }
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

  reset: () => {
    // T06：账号切换/登出/401 统一清理。中止在途流、递增世代使旧异步 set 失效，
    // 清空消息/历史/loaded/幂等键/屏幕上下文，并清理当前用户作用域的 active-conversation。
    activeAbortController?.abort()
    activeAbortController = undefined
    if (streamTimer !== undefined) window.clearInterval(streamTimer)
    streamTimer = undefined
    loadPromise = null
    const epoch = bumpEpoch()
    void epoch
    clearActiveConversation()
    useCompanionStore.getState().setAiState('idle')
    set({
      messages: [],
      conversationId: null,
      loaded: false,
      loadedEpoch: 0,
      lastScreenContext: null,
      lastIdempotencyKey: null,
      history: [],
      historyLoaded: false,
    })
  },
}))
