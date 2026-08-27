import { describe, expect, it } from 'vitest'

import {
  buildQuestionAskedEvent,
  buildVoiceSessionEvent,
  createVoiceEndedGuard,
  sectionEventKey,
  shouldEmitSectionRead,
} from './events'

describe('shouldEmitSectionRead（缺口 1a：章节切换后仍发送）', () => {
  it('同一章节内相同小节不重复发送', () => {
    const last = { chapterId: 'c1', section: '第一节' }
    expect(shouldEmitSectionRead(last, 'c1', '第一节')).toBe(false)
  })

  it('同一章节内新小节发送一次', () => {
    const last = { chapterId: 'c1', section: '第一节' }
    expect(shouldEmitSectionRead(last, 'c1', '第二节')).toBe(true)
  })

  it('切换章节后即使 section_key 相同也必须发送', () => {
    const last = { chapterId: 'c1', section: '训练数据' }
    expect(shouldEmitSectionRead(last, 'c2', '训练数据')).toBe(true)
  })

  it('空小节名不发送', () => {
    expect(
      shouldEmitSectionRead({ chapterId: 'c1', section: null }, 'c1', undefined),
    ).toBe(false)
  })

  it('sectionEventKey 跨章节天然唯一', () => {
    expect(sectionEventKey('c1', '训练数据')).not.toBe(sectionEventKey('c2', '训练数据'))
  })
})

describe('buildQuestionAskedEvent（缺口 1b/1c：提问事件可追溯到会话）', () => {
  const readerContext = {
    bookId: 'b1',
    chapterId: 'c1',
    pageType: 'chapter_reader' as const,
  }

  it('无真实 conversationId 时拒绝构造（不可追溯则不发）', () => {
    expect(
      buildQuestionAskedEvent({
        screenContext: readerContext,
        conversationId: null,
        source: 'composer',
      }),
    ).toBeNull()
  })

  it('自由输入：携带会话/书/章/学习会话关联与来源标记', () => {
    const event = buildQuestionAskedEvent({
      screenContext: readerContext,
      conversationId: 'conv-9',
      sessionId: 'sess-3',
      source: 'composer',
    })
    expect(event).not.toBeNull()
    expect(event!.conversation_id).toBe('conv-9')
    expect(event!.book_id).toBe('b1')
    expect(event!.chapter_id).toBe('c1')
    expect(event!.session_id).toBe('sess-3')
    expect((event!.payload as Record<string, unknown>).source).toBe('composer')
  })

  it('选中提问：额外携带 selected_text 与内容块/知识点', () => {
    const event = buildQuestionAskedEvent({
      screenContext: readerContext,
      conversationId: 'conv-9',
      blockId: 'blk-1',
      kpIds: ['kp1', 'kp2'],
      selectedText: '什么是规律',
      source: 'selection',
    })
    expect(event!.block_id).toBe('blk-1')
    expect(event!.knowledge_point_ids).toEqual(['kp1', 'kp2'])
    expect((event!.payload as Record<string, unknown>).selected_text).toBe('什么是规律')
  })
})

describe('createVoiceEndedGuard（缺口 1d：ENDED 恰好一次）', () => {
  it('未开始时消费返回 null', () => {
    const guard = createVoiceEndedGuard()
    expect(guard.isActive()).toBe(false)
    expect(guard.consumeEnded()).toBeNull()
  })

  it('start 后首次消费返回会话 id，第二次并发触发不再返回', () => {
    const guard = createVoiceEndedGuard()
    guard.markStarted('conv-voice')
    expect(guard.isActive()).toBe(true)
    expect(guard.consumeEnded()).toBe('conv-voice')
    expect(guard.consumeEnded()).toBeNull()
    expect(guard.isActive()).toBe(false)
  })

  it('重新 markStarted 开启新一轮语音会话', () => {
    const guard = createVoiceEndedGuard()
    guard.markStarted('conv-a')
    expect(guard.consumeEnded()).toBe('conv-a')
    guard.markStarted('conv-b')
    expect(guard.consumeEnded()).toBe('conv-b')
  })

  it('buildVoiceSessionEvent 携带类型与会话 id', () => {
    const started = buildVoiceSessionEvent('VOICE_SESSION_STARTED', 'conv-x')
    expect(started.event_type).toBe('VOICE_SESSION_STARTED')
    expect(started.conversation_id).toBe('conv-x')
    const ended = buildVoiceSessionEvent('VOICE_SESSION_ENDED', null)
    expect(ended.conversation_id).toBeUndefined()
  })
})
