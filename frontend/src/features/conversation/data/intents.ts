import type { ConversationIntent } from '../types'

/** 原型 currentIntentText 文案（逐字提取，未编造）；selectedText 支持 explain/selected 插值 */
export function currentIntentText(intent: ConversationIntent, selectedText = ''): string {
  const selected = selectedText ? `你刚刚选中了“${selectedText}”。` : ''
  const texts: Record<ConversationIntent, string> = {
    explain: `${selected}我先换一种讲法：训练数据不是机器背下来的答案，而是帮助它找规律的例子。比如让推荐系统看见你喜欢过的歌曲，它会尝试猜下一首。`,
    summary:
      '这一页可以先记住三件事：训练数据是例子；标签是我们希望机器学会的答案；例子是否有代表性，会影响机器之后的判断。',
    quiz: '好，我已经把当前章节的内容放进一份正式小测里。做完后，题目、答案和你使用过的提示都会保留在历史记录中。',
    'check-in': '我在。你现在卡在“训练数据”的定义，还是卡在它为什么会影响算法判断？',
    selected: `你选中的“${selectedText || '训练数据'}”位于当前章节的知识卡片里。我可以从它和“标签”的关系讲起。`,
    memory:
      '因为最近三次学习事件里，你都先要求看例子，再回到定义。这个偏好不是一次判断，而是霜铃逐渐观察到的线索。',
    'memory-dispute':
      '收到。我会把“你喜欢通过例子学习”先标记为“待确认”，接下来的讲解里我会多试几种方式，看看哪种对你更有效，再更新这条记忆。',
    'profile-question':
      '这份画像的每条判断都带着依据。比如“应用迁移”目前是“仍需观察”，不是因为一次答错，而是因为最近几次把概念放进新情境时，你都需要二级提示。这个判断会继续变化。',
    'profile-why-transfer':
      '“应用迁移”目前是“仍需观察”：最近三次把概念放进新情境的练习里，你有两次需要二级提示才能完成。等你有几次独立完成的应用题，霜铃就会更新这条判断。',
    'profile-why-pace':
      '连续三次学习里，你都在约 18 分钟的理论讲解后主动要求休息或提问，所以霜铃把节奏记成“短时、多轮”，并在长段落后安排一次互动。',
    'profile-why-question':
      '“提问习惯”来自最近 3 次对话：你从只问“这是什么”，慢慢开始追问“为什么会这样”。这说明你不再只想要答案，开始关心答案从哪里来。',
    'profile-why-change':
      '“最近变化”来自最近 3 次关于训练数据和算法偏见的对话，其中 2 次你主动追问了例子背后的原因。它不来自某一次测验，而是多次对话里慢慢出现的变化。',
    'presence-ask':
      '我在。你昨天两次追问了“标签”的定义，等读到知识卡片时我们可以再展开。现在想继续第 3 章，还是先聊点别的？',
    'today-learn':
      '今天的建议是：先花 12 分钟把「训练数据」这一节读完，再做一道随堂小测巩固。我会一直在旁边，随时可以问我。',
    'continue-yesterday':
      '你昨天停在「训练数据」的知识卡片，还问过“标签”的定义。我们从那里接着读，还是先花一分钟回顾一下？',
    'recent-status':
      '最近一周：概念理解越来越稳，提问也从“是什么”变成了“为什么”。唯一要留意的，是把概念放进新情境的应用迁移。',
    'recommend-next':
      '我推荐《和算法相处》：它正好接在「训练数据」之后，讲算法参与选择时怎样保留自己的判断，一共 6 章、约 70 分钟。',
    'book-fit':
      '《机器人会怎么想？》适合你：你喜欢从生活例子出发，这本书每章都从一个真实机器人案例开始，5 章、每章约 13 分钟。',
    'book-why-1':
      '《AI 不是魔法》你正在读：已经到第 3 章，而且最近两次测验里“训练数据”的连接还不够稳，继续读下去正好把概念用起来。',
    'book-why-2':
      '因为你最近对机器人表现出兴趣，而且这本书每章从真实案例出发，正好符合你“先例子、后定义”的学习偏好。',
    'book-why-3':
      '「训练数据」之后你会遇到“算法偏见”，《和算法相处》正好接着讲人怎么保留判断。读完第 3 章再开始，衔接最顺。',
    'give-example':
      '举个例子：给音乐推荐系统看你喜欢过的歌，它就能猜下一首。训练数据就是它看过的那些歌，标签就是“喜欢 / 不喜欢”。',
    'give-hint': '先回忆一下：训练数据是让机器背答案，还是从例子里找规律？',
    'another-way': '换一种讲法：把训练数据想成你教小狗认识球时，反复拿给它看的那些例子。',
    'why-wrong':
      '第 2 题里，训练数据只有一种狗的图片，机器学到的规律就是“四只脚、毛茸茸 = 狗”，所以遇到猫也会判断成狗。它没有“先问一问”的能力。',
    'quiz-requestion':
      '当然可以。第 2 题我们当时停在“训练数据提供的是例子，还是规则”。现在再看一遍：例子只有一种，机器学到的规律就变窄了。要不要我再出一个类似的题？',
    'quiz-detail':
      '这份历史测验会展示当时的原题、你的答案和提示记录，不会重新生成一份“看起来差不多”的题。',
  }
  return texts[intent] ?? '我会把当前页面、这段对话和你最近的学习线索一起考虑。'
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
  'quiz-requestion': 'thinking',
  quiz: 'encouraging',
}
