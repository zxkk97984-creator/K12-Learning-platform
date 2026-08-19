import { expect, test } from '@playwright/test'

// Phase 7 验收：画像页展示真实 ProfileInsight（5 档定性）+ 证据追溯 + episodes。
test('画像页加载真实 insights、展开证据与情节详情', async ({ page, request }) => {
  const loginResponse = await request.post('/api/v1/auth/login', {
    data: { username: 'xiaoming', password: 'demo123' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const accessToken = (await loginResponse.json()).data.access_token
  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, accessToken)

  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: '霜铃眼中的你。' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '当前表现' })).toBeVisible()

  // 5 档定性标签（偏弱/一般/较稳定/较强/仍需观察），不出现百分比/分数
  await expect(page.locator('text=/偏弱|一般|较稳定|较强|仍需观察/').first()).toBeVisible()
  await expect(page.getByText(/%|score|正确率/)).toHaveCount(0)

  // 证据追溯：展开「为什么？」
  await page.getByRole('button', { name: '为什么？' }).first().click()
  await expect(page.getByText('判断依据（真实学习记录）：')).toBeVisible()
  await expect(page.locator('text=/测验记录|课程对话|学习时段|阅读进度/').first()).toBeVisible()

  // 学习情节 + 详情
  await expect(page.getByRole('heading', { name: '学习情节' })).toBeVisible()
  await page.getByRole('button', { name: '详情' }).first().click()
  await expect(page.getByText(/关联事件：\d+ 条/)).toBeVisible()
})
