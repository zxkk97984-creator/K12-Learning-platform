// Phase 3 缺口修复：把「事件是否发送 / 事件载荷」的判定抽成纯函数，
// 让关键行为（章节切换后 SECTION_READ、提问事件关联会话、语音结束恰好一次）
// 可以在不挂载重型页面的情况下被直接验证。

import type { ScreenContext } from '@/features/screen-context/types'
import type { CreateLearningEventInput, LearningEventType } from '@/shared/api/learning-service'

/** 事件与真实业务对象的关联字段（全部可选，按可用性携带）。 */
export interface EventLinkage {
  blockId?: string | null
  kpIds?: string[]
  conversationId?: string | null
  sessionId?: string | null
}

/**
 * SECTION_READ 去重决策：
 * - 同一章节内相同小节不重复；
 * - 章节切换后（chapterId 变化），即使 section_key 与上一章相同也必须发一次。
 */
export function shouldEmitSectionRead(
  last: { chapterId: string | null; section: string | null },
  chapterId: string,
  sectionKey: string | null | undefined,
): boolean {
  if (!sectionKey) return false
  if (last.chapterId !== chapterId) return true
  return last.section !== sectionKey
}

/** 事件去重键：显式包含章节维度，杜绝跨章节同名小节被误判为重复。 */
export function sectionEventKey(chapterId: string, sectionKey: string): string {
  return `${chapterId}:section:${sectionKey}`
}

interface QuestionAskedInput {
  screenContext: Pick<ScreenContext, 'bookId' | 'chapterId' | 'pageType'>
  conversationId?: string | null
  sessionId?: string | null
  blockId?: string | null
  kpIds?: string[]
  /** 选中文本提问时携带；自由输入时不带 */
  selectedText?: string
  source: 'composer' | 'selection' | 'quick-action'
}

/**
 * 构造 QUESTION_ASKED 事件输入；必须携带真实 conversation_id 才返回，
 * 保证事件可追溯到会话。book/chapter 来自当前真实 ScreenContext。
 */
export function buildQuestionAskedEvent(
  input: QuestionAskedInput,
): CreateLearningEventInput | null {
  if (!input.conversationId) return null
  return {
    event_type: 'QUESTION_ASKED',
    occurred_at: new Date().toISOString(),
    ...(input.screenContext.bookId ? { book_id: input.screenContext.bookId } : {}),
    ...(input.screenContext.chapterId ? { chapter_id: input.screenContext.chapterId } : {}),
    ...(input.sessionId ? { session_id: input.sessionId } : {}),
    ...(input.blockId ? { block_id: input.blockId } : {}),
    ...(input.kpIds && input.kpIds.length > 0 ? { knowledge_point_ids: input.kpIds } : {}),
    conversation_id: input.conversationId,
    payload: {
      source: input.source,
      ...(input.selectedText ? { selected_text: input.selectedText } : {}),
    },
  }
}

/**
 * 语音会话结束守卫：start 成功后标记，ended 事件只允许被消费一次，
 * stop 与组件卸载并发触发也不会双发。
 */
export interface VoiceEndedGuard {
  markStarted: (conversationId: string | null) => void
  isActive: () => boolean
  /** 返回需要上报的 conversation_id；无活跃会话或已消费过则返回 null */
  consumeEnded: () => string | null
}

export function createVoiceEndedGuard(): VoiceEndedGuard {
  let activeConversationId: string | null = null
  let consumed = false
  return {
    markStarted(conversationId) {
      activeConversationId = conversationId
      consumed = false
    },
    isActive: () => activeConversationId !== null && !consumed,
    consumeEnded() {
      if (activeConversationId === null || consumed) return null
      consumed = true
      const id = activeConversationId
      activeConversationId = null
      return id
    },
  }
}

/** 语音开始/结束事件的统一构造（保证 conversation_id 可追溯）。 */
export function buildVoiceSessionEvent(
  eventType: Extract<LearningEventType, 'VOICE_SESSION_STARTED' | 'VOICE_SESSION_ENDED'>,
  conversationId?: string | null,
): CreateLearningEventInput {
  return {
    event_type: eventType,
    occurred_at: new Date().toISOString(),
    ...(conversationId ? { conversation_id: conversationId } : {}),
    payload: { channel: 'voice-ws' },
  }
}

/**
 * 当前活跃 LearningSession 的跨组件只读注册表。
 * ReaderPage 创建/结束时写入；ChatComposer 等无 props 关联的入口读取，
 * 使 QUESTION_ASKED / 语音事件能关联到真实学习会话。
 */
let currentLearningSessionId: string | null = null

export function setCurrentLearningSessionId(sessionId: string | null): void {
  currentLearningSessionId = sessionId
}

export function getCurrentLearningSessionId(): string | null {
  return currentLearningSessionId
}
