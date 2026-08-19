import { expect, test } from '@playwright/test'

const MEMORY_CONTENT = 'E2E 记忆验证：喜欢通过真实例子学习'

test.describe('记忆管理真实 API', () => {
  let accessToken = ''

  test.beforeAll(async ({ request }) => {
    const response = await request.post('/api/v1/auth/login', {
      data: { username: 'xiaoming', password: 'demo123' },
    })
    expect(response.ok()).toBeTruthy()
    accessToken = (await response.json()).data.access_token
  })

  test('确认与忘记操作在刷新后保持', async ({ page }) => {
    await page.addInitScript((token) => {
      window.localStorage.setItem('shuangling-access-token', token)
    }, accessToken)

    await page.goto('/profile/memories')
    const card = page.locator('li').filter({ hasText: MEMORY_CONTENT }).first()
    await expect(card).toBeVisible()

    await card.getByRole('button', { name: '为什么？' }).click()
    await expect(card.getByText('课程对话')).toBeVisible()

    await card.getByRole('button', { name: '确认正确' }).click()
    await expect(card.getByText('✓ 已确认')).toBeVisible()

    await page.reload()
    const reloadedCard = page.locator('li').filter({ hasText: MEMORY_CONTENT }).first()
    await expect(reloadedCard.getByText('✓ 已确认')).toBeVisible()

    await reloadedCard.getByRole('button', { name: '忘记这条' }).click()
    await expect(reloadedCard.getByText('已忘记')).toBeVisible()

    await page.reload()
    await page.getByRole('button', { name: '已忘记', exact: true }).click()
    const forgottenCard = page.locator('li').filter({ hasText: MEMORY_CONTENT }).first()
    await expect(forgottenCard.getByText('已忘记')).toBeVisible()
  })
})
