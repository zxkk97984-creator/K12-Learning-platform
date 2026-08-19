import { expect, test } from '@playwright/test'

test('设置页切换 AI 教师并刷新保持', async ({ page, request }) => {
  const loginResponse = await request.post('/api/v1/auth/login', {
    data: { username: 'xiaoming', password: 'demo123' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const accessToken = (await loginResponse.json()).data.access_token
  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, accessToken)

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: '我的 AI 教师' })).toBeVisible()
  const strictCard = page.locator('button').filter({ hasText: 'strict-mentor' })
  await expect(strictCard).toBeVisible()

  await strictCard.click()
  await expect(page.getByText('已切换 AI 教师')).toBeVisible()

  await page.reload()
  const reloadedStrict = page.locator('button').filter({ hasText: 'strict-mentor' })
  await expect(reloadedStrict).toHaveAttribute('aria-pressed', 'true')

  await page.locator('button').filter({ hasText: 'shuangling' }).click()
  await expect(page.getByText('已切换 AI 教师')).toBeVisible()
})
