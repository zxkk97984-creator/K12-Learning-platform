import { describe, expect, it } from 'vitest'

import { MockContentService } from './content-service'

const contentService = new MockContentService()

describe('MockContentService 筛选逻辑（学段/主题/搜索）', () => {
  it('getBooks 返回 12 本', async () => {
    expect(await contentService.getBooks()).toHaveLength(12)
  })

  it('学段筛选：PRIMARY=小学 3 本（b8~b10），SENIOR=高中 4 本', async () => {
    const primary = await contentService.getBooks({ stage: 'PRIMARY' })
    expect(primary.map((book) => book.book_id)).toEqual(['b8', 'b9', 'b10'])
    const senior = await contentService.getBooks({ stage: 'SENIOR' })
    expect(senior.map((book) => book.book_id)).toEqual(['b6', 'b7', 'b11', 'b12'])
  })

  it('主题筛选：机器人 2 本（b2/b8）', async () => {
    const robots = await contentService.getBooks({ topic: '机器人' })
    expect(robots.map((book) => book.book_id).sort()).toEqual(['b2', 'b8'])
  })

  it('搜索命中 title/keywords/tags（「训练」→ b1/b12）', async () => {
    const result = await contentService.getBooks({ search: '训练' })
    expect(result.map((book) => book.book_id).sort()).toEqual(['b1', 'b12'])
  })

  it('组合筛选：小学 + 数据 = b10', async () => {
    const result = await contentService.getBooks({ stage: 'PRIMARY', topic: '数据' })
    expect(result.map((book) => book.book_id)).toEqual(['b10'])
  })
})
