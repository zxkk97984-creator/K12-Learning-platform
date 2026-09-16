import type { Conversation, Message } from '@/entities/conversation/types'

/** 原型 state.messages 初始 4 条 + 随 quiz 生成的 tool/quiz 消息（meta 展示字符串不落库） */
export const mockMessages: Message[] = [
  {
    message_id: 'msg-1',
    conversation_id: 'conv-1',
    role: 'TEACHER',
    type: 'TEXT',
    content: '我看到你现在在《AI 不是魔法》的“训练数据”这一节。你想先用生活里的例子理解，还是直接看定义？',
    metadata: {},
    sequence: 1,
    model_info: { provider: 'mock', model: 'mock-model' },
    created_at: '2026-08-18T20:10:00Z',
  },
  {
    message_id: 'msg-2',
    conversation_id: 'conv-1',
    role: 'STUDENT',
    type: 'TEXT',
    content: '那这里的“训练数据”具体指什么？',
    metadata: {},
    sequence: 2,
    model_info: null,
    created_at: '2026-08-18T20:11:00Z',
  },
  {
    message_id: 'msg-3',
    conversation_id: 'conv-1',
    role: 'TEACHER',
    type: 'TEXT',
    content:
      '可以把它想成你教小狗认识球时，反复拿给它看的那些例子。它们帮助机器发现：不同的例子之间，哪些特征会和某个答案一起出现。',
    metadata: {},
    sequence: 3,
    model_info: { provider: 'mock', model: 'mock-model' },
    created_at: '2026-08-18T20:11:05Z',
  },
  {
    message_id: 'msg-4',
    conversation_id: 'conv-1',
    role: 'TEACHER',
    type: 'TOOL_STATUS',
    content: '测验已创建 · 正式测验已记录',
    metadata: { tool_state: 'done' },
    sequence: 4,
    model_info: { provider: 'mock', model: 'mock-model' },
    created_at: '2026-08-18T20:12:00Z',
  },
  {
    message_id: 'msg-5',
    conversation_id: 'conv-1',
    role: 'TEACHER',
    type: 'QUIZ',
    content: '根据这一段内容，试一道小题。',
    metadata: { quiz_session_id: 'q1' },
    sequence: 5,
    model_info: { provider: 'mock', model: 'mock-model' },
    created_at: '2026-08-18T20:12:01Z',
  },
]

export const mockConversation: Conversation = {
  conversation_id: 'conv-1',
  student_id: 'stu-xiaoming',
  teacher_role_id: 'role-shuangling',
  title: '课程对话',
  status: 'ACTIVE',
  channel: 'TEXT',
  current_page_context: {
    route: '/learn/b1/ch3',
    page_type: 'chapter_reader',
    book_id: 'b1',
    chapter_id: 'ch3',
    chapter_title: '训练数据',
    visible_section: '训练数据 · 定义',
    selected_text: null,
    knowledge_points: ['training_data'],
    actions: ['explain', 'summary', 'quiz'],
  },
  recent_messages: mockMessages,
  conversation_summary: null,
  created_at: '2026-08-18T20:10:00Z',
  updated_at: '2026-08-18T20:12:01Z',
  last_message_at: '2026-08-18T20:12:01Z',
}

/** 原型 QUICK_ACTIONS（按页面 → [intent, label][]） */
export const QUICK_ACTIONS: Record<string, [string, string][]> = {
  home: [
    ['today-learn', '今天学什么？'],
    ['continue-yesterday', '继续昨天的内容'],
    ['recent-status', '看看最近学习状态'],
  ],
  library: [
    ['recommend-next', '推荐下一本'],
    ['book-fit', '这本书适合我吗？'],
  ],
  reader: [
    ['explain', '解释这里'],
    ['give-example', '举个例子'],
    ['summary', '总结本页'],
    ['quiz', '给我出题'],
  ],
  quizzes: [
    ['give-hint', '给我一点提示'],
    ['another-way', '换一种讲法'],
    ['why-wrong', '为什么这个答案错了？'],
  ],
  'quiz-detail': [
    ['another-way', '换一种讲法'],
    ['why-wrong', '为什么这个答案错了？'],
  ],
  profile: [
    ['profile-question', '为什么这样判断我？'],
    ['profile-why-change', '最近我有什么变化？'],
  ],
}
