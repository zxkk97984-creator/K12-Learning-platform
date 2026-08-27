import { describe, expect, it } from 'vitest'

import type { ConversationIntent } from '../types'
import { currentIntentText } from './intents'

const ALL_INTENTS: ConversationIntent[] = [
  'explain', 'summary', 'quiz', 'check-in', 'selected', 'memory', 'memory-dispute',
  'profile-question', 'profile-why-transfer', 'profile-why-pace', 'profile-why-question',
  'profile-why-change', 'presence-ask', 'today-learn', 'continue-yesterday',
  'recent-status', 'recommend-next', 'book-fit', 'book-why-1', 'book-why-2',
  'book-why-3', 'give-example', 'give-hint', 'another-way', 'why-wrong',
  'quiz-requestion', 'quiz-detail',
]

/** 这些字串只可能来自编造的具体学习事实（书名/章节/次数/时长/日期） */
const FORBIDDEN = [
  '训练数据', '第 3 章', '第3章', '18 分钟', '最近 3 次', '最近三次',
  '你昨天', '昨天两次', '《和算法相处》', '《机器人会怎么想？》', '12 分钟',
  '应用迁移', '标签的定义',
]

describe('currentIntentText（Phase 4：不得伪造学习事实）', () => {
  it('全部 intent 均返回非空通用引导语', () => {
    for (const intent of ALL_INTENTS) {
      const text = currentIntentText(intent)
      expect(text.trim().length).toBeGreaterThan(0)
    }
  })

  it('任何 intent 都不包含硬编码的书名/章节/次数/日期等事实', () => {
    for (const intent of ALL_INTENTS) {
      const text = currentIntentText(intent)
      for (const forbidden of FORBIDDEN) {
        expect(text).not.toContain(forbidden)
      }
    }
  })

  it('selected/explain 支持选中文本插值（用户真实输入，非伪造）', () => {
    expect(currentIntentText('explain', '训练数据')).toContain('你刚刚选中了“训练数据”。')
    expect(currentIntentText('selected', '标签')).toContain('你刚刚选中了“标签”')
    // 未选中文本时不得回退到具体章节名词
    expect(currentIntentText('selected')).not.toContain('训练数据')
  })
})
