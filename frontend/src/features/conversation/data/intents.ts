import type { ConversationIntent } from '../types'

/**
 * Phase 4 整改：意图不再携带任何「假装知道学习事实」的本地文案
 * （具体书名/章节/次数/日期等一律由后端基于真实数据生成）。
 * 这里只保留与具体事实无关的通用引导语；真实内容全部来自后端 SSE。
 */
export function currentIntentText(intent: ConversationIntent, selectedText = ''): string {
  const selected = selectedText ? `你刚刚选中了“${selectedText}”。` : ''
  const texts: Record<ConversationIntent, string> = {
    explain: `${selected}请结合我当前看到的内容解释一下。`,
    summary: '请帮我总结当前这一页的要点。',
    quiz: '给我出题',
    'check-in': '你在吗？',
    selected: selected || '请解释我选中的内容。',
    memory: '根据我的学习记录，你观察到了哪些关于我的记忆？',
    'memory-dispute': '我想质疑一条记忆，请说明它的依据并允许我修改。',
    'profile-question': '为什么你会这样判断我的学习画像？请给出可追溯的依据。',
    'profile-why-transfer': '为什么这条画像判断是当前结论？依据是什么？',
    'profile-why-pace': '为什么这样判断我的学习节奏？',
    'profile-why-question': '为什么这样判断我的提问习惯？',
    'profile-why-change': '最近我的学习有什么变化？依据是什么？',
    'presence-ask': '你在吗？',
    'today-learn': '结合我的进度，今天建议学什么？',
    'continue-yesterday': '从我上次的学习位置继续，应该从哪里开始？',
    'recent-status': '看看我最近的学习状态。',
    'recommend-next': '推荐下一本适合我的书，并说明理由。',
    'book-fit': '这本书适合我吗？为什么？',
    'book-why-1': '为什么推荐这本书？',
    'book-why-2': '这本书为什么适合我？',
    'book-why-3': '下一步为什么学这个？',
    'give-example': '能举一个和当前内容相关的例子吗？',
    'give-hint': '给我一点提示，不要直接给答案。',
    'another-way': '换一种讲法解释当前内容。',
    'why-wrong': '我这道题为什么错了？请结合题目解析说明。',
    'explain-question': '请讲解这道题：结合题目、我的作答与解析，说清楚为什么。',
    'quiz-requestion': '再出一道类似的题。',
    'quiz-detail': '解释这份测验记录里的错题。',
  }
  return texts[intent] ?? '我会结合当前页面和你最近的学习线索来回答。'
}

/** intent → companion aiState（原型 openCompanion 映射；quiz 走 encouraging 特殊流程） */
export const INTENT_AI_STATE: Partial<Record<ConversationIntent, 'idle' | 'listening' | 'thinking' | 'speaking' | 'happy' | 'confused' | 'encouraging'>> = {
  'profile-question': 'thinking',
  memory: 'thinking',
  'memory-dispute': 'thinking',
  'profile-why-transfer': 'thinking',
  'profile-why-pace': 'thinking',
  'profile-why-question': 'thinking',
  'profile-why-change': 'thinking',
  'book-why-1': 'thinking',
  'book-why-2': 'thinking',
  'book-why-3': 'thinking',
  'book-fit': 'thinking',
  'recommend-next': 'thinking',
  'why-wrong': 'thinking',
  'explain-question': 'thinking',
  'quiz-requestion': 'thinking',
  quiz: 'encouraging',
}
