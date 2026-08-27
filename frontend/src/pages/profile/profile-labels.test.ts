import { describe, expect, it } from 'vitest'

import { buildProfileExportJson, parseProfileFrontmatter } from './profile-labels'

describe('parseProfileFrontmatter（Phase 4：档案编辑真实持久化）', () => {
  it('解析合法枚举与年级，忽略非法值', () => {
    const md = `---
name: 小明
grade: 8
preferred_explanation_style: example_based
preferred_difficulty: HARD
preferred_session_length: SHORT
---
正文
- 学习目标：期末 AI 成绩提升`
    const patch = parseProfileFrontmatter(md)
    expect(patch.grade).toBe(8)
    expect(patch.preferred_explanation_style).toBe('EXAMPLE_BASED')
    expect(patch.preferred_difficulty).toBe('HARD')
    expect(patch.preferred_session_length).toBe('SHORT')
    expect(patch.learning_goal).toBe('期末 AI 成绩提升')
  })

  it('非法枚举/年级被拒绝而不是写库', () => {
    const patch = parseProfileFrontmatter(
      '---\ngrade: 99\npreferred_difficulty: IMPOSSIBLE\n---\n- 学习目标：',
    )
    expect(patch.grade).toBeUndefined()
    expect(patch.preferred_difficulty).toBeUndefined()
    // 空学习目标不写入
    expect(patch.learning_goal).toBeUndefined()
  })
})

describe('buildProfileExportJson（Phase 4：真实数据导出）', () => {
  it('导出内容来自传入的真实服务数据并包含全部维度', () => {
    const json = buildProfileExportJson({
      profile: { nickname: '小明', grade: 8, learning_days: 3 },
      preferences: { preferred_explanation_style: 'EXAMPLE_BASED' },
      insights: [{ insight_id: 'i1', description: '能快速联系概念' }],
      memories: [
        { memory_id: 'm1', content: '喜欢例子' },
        { memory_id: 'm2', content: '偏好短时学习' },
      ],
    })
    const parsed = JSON.parse(json) as Record<string, unknown>
    expect(parsed.profile).toMatchObject({ nickname: '小明', learning_days: 3 })
    expect(parsed.preferences).toMatchObject({ preferred_explanation_style: 'EXAMPLE_BASED' })
    expect((parsed.insights as unknown[]).length).toBe(1)
    expect((parsed.memories as unknown[]).length).toBe(2)
    expect(typeof parsed.exported_at).toBe('string')
  })
})
