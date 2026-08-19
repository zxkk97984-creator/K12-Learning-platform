/**
 * 临时 Recommendation mock（Phase 1；未来由 0-C Recommendation 实体 + 推荐 Skill 提供）。
 * 文案逐字取自原型：home recommend-card + library book-why-1/2/3。
 */

export interface HomeRecommendation {
  title: string
  copy: string
  evidenceTitle: string
  evidence: string
}

export interface BookRecommendation {
  bookId: string
  reason: string
}

export const homeRecommendation: HomeRecommendation = {
  title: '先复习“训练数据”，再进入算法偏见。',
  copy: '这样你会更容易理解：机器学到的，不只取决于算法，还取决于它看过什么。',
  evidenceTitle: '为什么推荐？',
  evidence: '你昨天在测验里两次回到“标签”的定义，说明这个连接值得再巩固一次。',
}

export const bookRecommendations: BookRecommendation[] = [
  {
    bookId: 'b1',
    reason:
      '《AI 不是魔法》你正在读：已经到第 3 章，而且最近两次测验里“训练数据”的连接还不够稳，继续读下去正好把概念用起来。',
  },
  {
    bookId: 'b2',
    reason:
      '因为你最近对机器人表现出兴趣，而且这本书每章从真实案例出发，正好符合你“先例子、后定义”的学习偏好。',
  },
  {
    bookId: 'b3',
    reason:
      '「训练数据」之后你会遇到“算法偏见”，《和算法相处》正好接着讲人怎么保留判断。读完第 3 章再开始，衔接最顺。',
  },
]
