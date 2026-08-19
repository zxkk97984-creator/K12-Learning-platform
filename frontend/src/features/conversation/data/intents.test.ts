import { describe, expect, it } from 'vitest'

import { currentIntentText } from './intents'

const ALL_INTENTS = [
  'explain',
  'summary',
  'quiz',
  'check-in',
  'selected',
  'memory',
  'memory-dispute',
  'profile-question',
  'profile-why-transfer',
  'profile-why-pace',
  'profile-why-question',
  'profile-why-change',
  'presence-ask',
  'today-learn',
  'continue-yesterday',
  'recent-status',
  'recommend-next',
  'book-fit',
  'book-why-1',
  'book-why-2',
  'book-why-3',
  'give-example',
  'give-hint',
  'another-way',
  'why-wrong',
  'quiz-requestion',
  'quiz-detail',
] as const

describe('currentIntentText（27 intent）', () => {
  it('27 个 intent 全部返回非空文案', () => {
    expect(ALL_INTENTS).toHaveLength(27)
    for (const intent of ALL_INTENTS) {
      const text = currentIntentText(intent)
      expect(text.trim().length).toBeGreaterThan(0)
    }
  })

  it('explain/selected 支持 selectedText 插值', () => {
    expect(currentIntentText('explain', '训练数据')).toContain('你刚刚选中了“训练数据”。')
    expect(currentIntentText('selected', '标签')).toContain('你选中的“标签”')
    expect(currentIntentText('selected')).toContain('你选中的“训练数据”')
  })

  it('未知 intent 走兜底文案', () => {
    expect(currentIntentText('not-a-real-intent' as never)).toBe(
      '我会把当前页面、这段对话和你最近的学习线索一起考虑。',
    )
  })
})
